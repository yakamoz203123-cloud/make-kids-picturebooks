"""Small user-facing workflow entry points for picturebook production.

This module is intentionally an orchestrator, not a second validation system.
It routes to the existing read-only preflight, queue, authorization, and
delivery-release modules while returning a compact JSON-friendly status.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from build_pure_image_delivery import _book_dir, _project_root
from generation_queue import (
    ACTIVE_STATUSES,
    DONE_STATUSES,
    RETRYABLE_STATUSES,
    DEFAULT_MAX_ATTEMPTS,
    _load_queue,
    authorize_generation,
    claim_job,
    init_queue,
)
from project_preflight import MODES, preflight_project
from release_pure_image_delivery import release_delivery


SAFE_EXIT_STATUSES = {
    "passed",
    "claimed",
    "waiting",
    "complete",
    "released",
    "reused",
}


def _book_and_queue(
    project: str | Path,
    book_id: str,
    version: str | None,
    queue_path: str | Path | None,
) -> tuple[Path, Path]:
    root = _project_root(project)
    book_dir = _book_dir(root, book_id, version)
    resolved_queue = (
        Path(queue_path).resolve()
        if queue_path is not None
        else book_dir / "review" / "production-queue.json"
    )
    return book_dir, resolved_queue


def _doctor_next_action(report: Mapping[str, Any]) -> str:
    if report.get("status") == "passed":
        return "可以运行 workflow.py resume；正式生图前仍需明确用户授权。"
    return "先根据 blockers 和 fix_advice 修复项目，再重新运行 doctor。"


def _passed_checks(report: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("check"))
        for item in report.get("passed", [])
        if isinstance(item, Mapping) and item.get("check")
    }


def _gate_value(checks: set[str], required: tuple[str, ...]) -> str:
    return "passed" if all(check in checks for check in required) else "hold"


def _doctor_summary(report: Mapping[str, Any], *, elapsed_ms: int | str = "unknown") -> dict[str, Any]:
    """Project one full preflight report into a compact, auditable handoff."""
    checks = _passed_checks(report)
    status = str(report.get("status") or "blocked")
    return {
        "status": status,
        "phase": report.get("phase"),
        "mode": report.get("mode"),
        "project_root": report.get("project_root"),
        "book_key": report.get("book_key"),
        "version": report.get("version"),
        "page_count": report.get("page_count"),
        "plan_fingerprint": report.get("plan_fingerprint"),
        "elapsed_ms": elapsed_ms,
        "gate_summary": {
            "assets": _gate_value(
                checks,
                ("approved_asset_and_style_references", "production_dependency_closure"),
            ),
            "content": _gate_value(checks, ("research_traceability", "content_gate")),
            "storyboard": _gate_value(checks, ("page_numbers_match", "page_text_matches_storyboard")),
            "pages": _gate_value(checks, ("page_manifest_validation",)),
        },
        "input_snapshot": {
            "status": "stable" if status == "passed" else "unstable",
            "plan_fingerprint": report.get("plan_fingerprint"),
        },
        "generation_authorization": (
            "READY_FOR_USER_AUTHORIZATION" if status == "passed" else "HOLD"
        ),
        "image_generation": "SKIPPED",
        "blockers": list(report.get("blockers") or []),
        "warnings": list(report.get("warnings") or []),
        "image_model_calls": report.get("image_model_calls", 0),
        "write_operations": report.get("write_operations", 0),
        "next_action": _doctor_next_action(report),
    }


def _write_json_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target


def doctor(
    project: str | Path,
    book_id: str,
    *,
    version: str | None = None,
    mode: str = "strict",
    report_json: str | Path | None = None,
) -> dict[str, Any]:
    """Run the existing pre-generation gate and return a compact summary."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    started = time.perf_counter()
    report = preflight_project(
        project,
        book_id,
        version=version,
        phase="pre_generation",
        mode=mode,
    )
    result = _doctor_summary(
        report,
        elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
    )
    if report_json is not None:
        result["report_path"] = str(_write_json_report(report_json, report))
    return result


def _state_counts(state: Mapping[str, Any]) -> dict[str, int]:
    counts = {key: 0 for key in ("pending", "running", "retryable", "failed", "completed", "cached")}
    for job in state.get("jobs", []):
        status = str(job.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _available_authorization(state: Mapping[str, Any], job: Mapping[str, Any]) -> dict[str, Any] | None:
    page = str(int(job["page"]))
    for authorization in state.get("generation_authorizations", []):
        if not isinstance(authorization, Mapping):
            continue
        try:
            available = int(authorization.get("max_calls", 0)) - int(authorization.get("used_calls", 0))
        except (TypeError, ValueError):
            continue
        if available < 1:
            continue
        page_fingerprints = authorization.get("page_fingerprints")
        if isinstance(page_fingerprints, Mapping) and page_fingerprints.get(page) != job.get("request_fingerprint"):
            continue
        return dict(authorization)
    return None


def _pending_unknown_pages(state: Mapping[str, Any], jobs: list[Mapping[str, Any]]) -> list[int]:
    """Find failed page jobs whose current request needs explicit recovery."""
    unknown_request_ids = {
        str(record.get("request_id"))
        for record in state.get("request_lifecycle", [])
        if isinstance(record, Mapping)
        and record.get("terminal_state") in {"pending_unknown", "timed_out"}
        and record.get("request_id")
    }
    return sorted(
        int(job["page"])
        for job in jobs
        if job.get("status") == "failed"
        and str(job.get("current_request_id")) in unknown_request_ids
    )


def _resume_summary(
    *,
    status: str,
    queue_path: Path,
    state: Mapping[str, Any],
    **fields: Any,
) -> dict[str, Any]:
    result = {
        "status": status,
        "queue_path": str(queue_path),
        "page_count": state.get("page_count"),
        "counts": _state_counts(state),
        "max_in_flight": state.get("max_in_flight"),
        "next_action": fields.pop("next_action", None),
    }
    result.update(fields)
    return result


def resume(
    project: str | Path,
    book_id: str,
    *,
    version: str | None = None,
    queue_path: str | Path | None = None,
    approval: str | None = None,
    max_calls: int = 1,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Reuse or initialize a queue and safely advance at most one page."""
    book_dir, resolved_queue = _book_and_queue(project, book_id, version, queue_path)
    # ``init_queue`` intentionally requeues a locally running job so a low-level
    # coordinator can recover after interruption.  The user-facing entry point
    # must not make that irreversible interpretation on its own: while a page
    # is marked running, report waiting and let the existing lifecycle commands
    # resolve it explicitly.
    if resolved_queue.is_file():
        existing = _load_queue(resolved_queue)
        if Path(existing["book_dir"]).resolve() != book_dir:
            raise ValueError("existing queue belongs to a different book directory")
        existing_running = sorted(
            int(job["page"])
            for job in existing.get("jobs", [])
            if isinstance(job, Mapping) and job.get("status") in ACTIVE_STATUSES
        )
        if existing_running:
            return _resume_summary(
                status="waiting",
                queue_path=resolved_queue,
                state=existing,
                running_pages=existing_running,
                next_action="先完成或明确处理运行中的页面，再继续领取下一页。",
            )
    state = init_queue(
        book_dir,
        resolved_queue,
        max_in_flight=1,
        max_attempts=max_attempts,
        allow_standalone_legacy=False,
        require_visual_review=True,
    )
    jobs = [job for job in state.get("jobs", []) if isinstance(job, Mapping)]
    running_pages = sorted(int(job["page"]) for job in jobs if job.get("status") in ACTIVE_STATUSES)
    if running_pages:
        return _resume_summary(
            status="waiting",
            queue_path=resolved_queue,
            state=state,
            running_pages=running_pages,
            next_action="先完成或明确处理运行中的页面，再继续领取下一页。",
        )

    unknown_pages = _pending_unknown_pages(state, jobs)
    if unknown_pages:
        return _resume_summary(
            status="blocked",
            queue_path=resolved_queue,
            state=state,
            blocked_pages=unknown_pages,
            reason="manual_intervention_required",
            next_action="先检查未知请求的产物；获得新授权后使用 authorize-recovery，再运行 claim-recovery。",
        )

    failed_pages = sorted(int(job["page"]) for job in jobs if job.get("status") == "failed")
    if failed_pages:
        return _resume_summary(
            status="blocked",
            queue_path=resolved_queue,
            state=state,
            blocked_pages=failed_pages,
            reason="retry_budget_exhausted_or_failed",
            next_action="先按底层队列规则处理失败页，不会自动重试。",
        )

    pending = [job for job in jobs if job.get("status") in RETRYABLE_STATUSES]
    if not pending:
        unknown_pages = sorted(
            int(job["page"])
            for job in jobs
            if job.get("status") not in DONE_STATUSES
        )
        if unknown_pages:
            return _resume_summary(
                status="blocked",
                queue_path=resolved_queue,
                state=state,
                blocked_pages=unknown_pages,
                reason="manual_intervention_required",
                next_action="检查 pending_unknown 或其他非终态页面，不会自动恢复。",
            )
        return _resume_summary(
            status="complete",
            queue_path=resolved_queue,
            state=state,
            next_action="所有页面已经完成或命中有效缓存；继续做页面审核和交付验收。",
        )

    job = pending[0]
    page = int(job["page"])
    authorization = _available_authorization(state, job)
    if authorization is None and approval is None and state.get("requires_user_authorization"):
        return _resume_summary(
            status="authorization_required",
            queue_path=resolved_queue,
            state=state,
            next_page=page,
            next_action="请明确授权后再次运行 resume --approval；入口不会自动批准。",
        )

    if authorization is None and state.get("requires_user_authorization"):
        authorization = authorize_generation(
            resolved_queue,
            approval=approval or "",
            max_calls=max_calls,
        )

    authorization_id = authorization.get("authorization_id") if authorization else None
    claimed = claim_job(resolved_queue, page, authorization_id=authorization_id)
    return _resume_summary(
        status="claimed",
        queue_path=resolved_queue,
        state=_load_queue(resolved_queue),
        page=page,
        job=claimed,
        authorization_id=authorization_id,
        next_action="执行这一页的实际图片调用；完成或失败记账后再运行 resume。",
    )


def deliver(
    project: str | Path,
    book_id: str,
    delivery: str | Path,
    *,
    version: str | None = None,
) -> dict[str, Any]:
    """Delegate delivery release to the existing final gate."""
    return release_delivery(project, book_id, delivery, version=version)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("doctor", help="read-only pre-generation project check")
    check.add_argument("project", type=Path)
    check.add_argument("book_id")
    check.add_argument("--version")
    check.add_argument("--mode", choices=sorted(MODES), default="strict")
    check.add_argument("--report-json", type=Path, help="write full evidence without printing it")

    continue_production = subparsers.add_parser("resume", help="reuse the queue and claim at most one next page")
    continue_production.add_argument("project", type=Path)
    continue_production.add_argument("book_id")
    continue_production.add_argument("--version")
    continue_production.add_argument("--queue-json", type=Path)
    continue_production.add_argument("--approval")
    continue_production.add_argument("--max-calls", type=int, default=1)
    continue_production.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)

    release = subparsers.add_parser("deliver", help="run the existing pre-delivery release gate")
    release.add_argument("project", type=Path)
    release.add_argument("book_id")
    release.add_argument("delivery", type=Path)
    release.add_argument("--version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor(
                args.project,
                args.book_id,
                version=args.version,
                mode=args.mode,
                report_json=args.report_json,
            )
        elif args.command == "resume":
            result = resume(
                args.project,
                args.book_id,
                version=args.version,
                queue_path=args.queue_json,
                approval=args.approval,
                max_calls=args.max_calls,
                max_attempts=args.max_attempts,
            )
        elif args.command == "deliver":
            result = deliver(args.project, args.book_id, args.delivery, version=args.version)
        else:  # pragma: no cover
            raise ValueError(f"unsupported command: {args.command}")
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in SAFE_EXIT_STATUSES else 2


if __name__ == "__main__":
    raise SystemExit(main())

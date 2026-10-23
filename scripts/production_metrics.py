"""Summarize picturebook production metrics without modifying a queue.

This module is intentionally read-only with respect to generation queue state.
It accepts the current schema_version=1 queue document and optional phase-event
records, then writes a deterministic JSON report.  The canonical metrics
contract always includes the fields documented by ``acceptance.md``.  A value
is ``"unknown"`` unless the queue or an explicit event/field makes it
observable; queue claims are not treated as image-model calls.  The older
field names remain as compatibility aliases for existing consumers.

``output_quality`` is an explicit review field: completed files never imply
that a book is approved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from production_timing import summarize_phase_events


SCHEMA_VERSION = 1
UNKNOWN = "unknown"
QUALITY_VALUES = {"pending", "approved"}
_IMAGE_GENERATION_EVENT_NAMES = {
    "image_generation_call",
    "image_generation_called",
    "image_generation_started",
    "image_request_started",
}
_MODEL_WAIT_EVENT_NAMES = {"model_wait", "model_waited"}
_COMPLETION_EVENT_NAMES = {
    "completed",
    "image_artifact_completed",
    "image_completed",
    "image_generation_completed",
}
_TIMESTAMP_KEYS = {
    "at",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "completed_at",
    "timestamp",
}


def _require_queue_state(queue_state: Mapping[str, Any]) -> None:
    if not isinstance(queue_state, Mapping):
        raise ValueError("queue state must be a JSON object")
    if type(queue_state.get("schema_version")) is not int or queue_state["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported queue schema: {queue_state.get('schema_version')!r}")
    jobs = queue_state.get("jobs")
    if not isinstance(jobs, list) or not all(isinstance(job, Mapping) for job in jobs):
        raise ValueError("queue jobs must be a list of objects")


def _events(value: Any, name: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        value = value.get("events")
    if not isinstance(value, list) or not all(isinstance(event, Mapping) for event in value):
        raise ValueError(f"{name} must be a list of event objects or an object containing events")
    return list(value)


def _merge_events(*streams: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Merge event streams while removing exact duplicate records."""
    merged: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for stream in streams:
        for event in stream:
            try:
                key = json.dumps(dict(event), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError):
                key = repr(sorted(event.items(), key=lambda item: str(item[0])))
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
    return merged


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_values(queue_state: Mapping[str, Any], jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> list[datetime]:
    values: list[datetime] = []
    records: list[Mapping[str, Any]] = [queue_state, *jobs, *events]
    for record in records:
        for key in _TIMESTAMP_KEYS:
            parsed = _timestamp(record.get(key))
            if parsed is not None:
                values.append(parsed)
    return values


def _page_key(record: Mapping[str, Any], fallback: int | None = None) -> tuple[str, Any] | None:
    page = _nonnegative_int(record.get("page"))
    if page is not None:
        return ("page", page)
    job_id = record.get("job_id")
    if job_id is not None and str(job_id).strip():
        return ("job", str(job_id))
    if fallback is not None:
        return ("index", fallback)
    return None


def _event_attempt_count(events: list[Mapping[str, Any]]) -> int:
    count = 0
    found = False
    for event in events:
        name = event.get("event")
        if name == "claimed":
            count += 1
            found = True
        elif name == "batch_claimed":
            pages = event.get("pages")
            attempts = event.get("attempts")
            batch_count = len(pages) if isinstance(pages, list) else len(attempts) if isinstance(attempts, list) else 1
            count += batch_count
            found = True
    return count if found else -1


def _completion_elapsed_by_page(events: list[Mapping[str, Any]]) -> tuple[dict[tuple[str, Any], list[int]], list[int]]:
    by_page: dict[tuple[str, Any], list[int]] = {}
    unkeyed: list[int] = []
    for event in events:
        if event.get("event") not in _COMPLETION_EVENT_NAMES:
            continue
        elapsed = _nonnegative_int(event.get("elapsed_ms"))
        if elapsed is None:
            continue
        key = _page_key(event)
        if key is None:
            unkeyed.append(elapsed)
        else:
            by_page.setdefault(key, []).append(elapsed)
    return by_page, unkeyed


def _recorded_image_elapsed(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> int | str:
    by_page, unkeyed = _completion_elapsed_by_page(events)
    total = 0
    observed = bool(by_page or unkeyed)
    job_keys: set[tuple[str, Any]] = set()
    for index, job in enumerate(jobs):
        job_key = _page_key(job, index)
        if job_key is not None:
            job_keys.add(job_key)
        event_values = by_page.get(job_key, []) if job_key is not None else []
        elapsed = _nonnegative_int(job.get("elapsed_ms"))
        if elapsed is None:
            total += sum(event_values)
            continue
        observed = True
        total += elapsed
        if event_values:
            remaining = list(event_values)
            for event_index in range(len(remaining) - 1, -1, -1):
                if remaining[event_index] == elapsed:
                    del remaining[event_index]
                    break
            total += sum(remaining)
    total += sum(
        value
        for key, values in by_page.items()
        if key not in job_keys
        for value in [sum(values)]
    )
    if not jobs:
        total += sum(unkeyed)
    return total if observed else UNKNOWN


def _failure_count(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> int | str:
    event_failures = sum(1 for event in events if event.get("event") == "failed")
    if event_failures:
        return event_failures
    if jobs and all("status" in job for job in jobs):
        failures = 0
        for job in jobs:
            errors = job.get("errors")
            if isinstance(errors, list):
                failures += len(errors)
            elif job.get("status") == "failed":
                failures += 1
        return failures
    if jobs and all(isinstance(job.get("errors"), list) for job in jobs):
        return sum(len(job["errors"]) for job in jobs)
    if events:
        return 0
    return UNKNOWN


def _retry_count(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]], attempts: int | str) -> int | str:
    failed_events = [event for event in events if event.get("event") == "failed"]
    if failed_events:
        return sum(1 for event in failed_events if event.get("retryable") is True)
    if jobs and all(_nonnegative_int(job.get("attempts")) is not None for job in jobs):
        return sum(max(_nonnegative_int(job.get("attempts")) - 1, 0) for job in jobs)
    return UNKNOWN


def _cache_hits(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> int | str:
    cached_keys: set[tuple[str, Any]] = set()
    unkeyed_events = 0
    for index, job in enumerate(jobs):
        if job.get("status") == "cached":
            key = _page_key(job, index)
            if key is not None:
                cached_keys.add(key)
    for event_index, event in enumerate(events):
        if event.get("event") not in {"cache_hit", "cached"}:
            continue
        key = _page_key(event)
        if key is None:
            unkeyed_events += 1
        else:
            cached_keys.add(key)
    if jobs or events:
        return len(cached_keys) + unkeyed_events
    return UNKNOWN


def _page_rework_count(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> int | str:
    resets = sum(1 for event in events if event.get("event") == "page_reset")
    if resets:
        return resets
    if jobs and all(_nonnegative_int(job.get("revision")) is not None for job in jobs):
        return sum(max(_nonnegative_int(job.get("revision")) - 1, 0) for job in jobs)
    return UNKNOWN


def _pages_completed(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> int | str:
    if jobs and all("status" in job for job in jobs):
        return sum(1 for job in jobs if job.get("status") in {"completed", "cached"})
    completed_keys: set[tuple[str, Any]] = set()
    unkeyed = 0
    for event in events:
        if event.get("event") not in {"completed", "cache_hit", "cached"}:
            continue
        key = _page_key(event)
        if key is None:
            unkeyed += 1
        else:
            completed_keys.add(key)
    if completed_keys or unkeyed:
        return len(completed_keys) + unkeyed
    return UNKNOWN


def _first_nonnegative(record: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        value = _nonnegative_int(record.get(key))
        if value is not None:
            return value
    return None


def _event_counter(
    events: list[Mapping[str, Any]],
    *,
    names: set[str],
    value_keys: Sequence[str],
) -> int | None:
    observed = False
    total = 0
    for event in events:
        event_name = event.get("event")
        explicit_value = _first_nonnegative(event, value_keys)
        if event_name in names:
            observed = True
            total += explicit_value if explicit_value is not None else 1
    return total if observed else None


def _attempt_count(jobs: list[Mapping[str, Any]], events: list[Mapping[str, Any]]) -> int | str:
    event_attempts = _event_attempt_count(events)
    if event_attempts >= 0:
        return event_attempts
    if jobs:
        values = [_nonnegative_int(job.get("attempts")) for job in jobs]
        if all(value is not None for value in values):
            return sum(value for value in values if value is not None)
    return UNKNOWN


def _field_sum(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> int | None:
    values: list[int] = []
    for record in records:
        value = _first_nonnegative(record, keys)
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def _image_generation_calls(
    queue_state: Mapping[str, Any],
    jobs: list[Mapping[str, Any]],
    queue_events: list[Mapping[str, Any]],
    phase_events: list[Mapping[str, Any]],
) -> int | str:
    event_value = _event_counter(
        [*queue_events, *phase_events],
        names=_IMAGE_GENERATION_EVENT_NAMES,
        value_keys=("count", "calls", "image_generation_calls", "generation_calls"),
    )
    if event_value is not None:
        return event_value
    state_value = _first_nonnegative(queue_state, ("image_generation_calls", "generation_calls"))
    if state_value is not None:
        return state_value
    job_value = _field_sum(jobs, ("image_generation_calls", "generation_calls"))
    return job_value if job_value is not None else UNKNOWN


def _model_wait_ms(
    queue_state: Mapping[str, Any],
    jobs: list[Mapping[str, Any]],
    queue_events: list[Mapping[str, Any]],
    phase_events: list[Mapping[str, Any]],
) -> int | str:
    event_value = _event_counter(
        [*queue_events, *phase_events],
        names=_MODEL_WAIT_EVENT_NAMES,
        value_keys=("model_wait_ms", "wait_ms", "duration_ms", "elapsed_ms"),
    )
    if event_value is not None:
        return event_value
    state_value = _first_nonnegative(queue_state, ("model_wait_ms",))
    if state_value is not None:
        return state_value
    job_value = _field_sum(jobs, ("model_wait_ms",))
    return job_value if job_value is not None else UNKNOWN


def _image_artifact_span_ms(
    queue_state: Mapping[str, Any],
    jobs: list[Mapping[str, Any]],
    queue_events: list[Mapping[str, Any]],
    phase_events: list[Mapping[str, Any]],
) -> int | str:
    metric_events = _merge_events(queue_events, phase_events)
    explicit = _first_nonnegative(queue_state, ("image_artifact_span_ms",))
    if explicit is not None:
        return explicit
    explicit = _field_sum([*jobs, *metric_events], ("image_artifact_span_ms",))
    if explicit is not None:
        return explicit
    return _recorded_image_elapsed(jobs, metric_events)


def _resume_events(
    queue_state: Mapping[str, Any],
    queue_events: list[Mapping[str, Any]],
) -> int | str:
    explicit = _first_nonnegative(queue_state, ("resume_events",))
    if explicit is not None:
        return explicit
    if "events" in queue_state or queue_events:
        return sum(1 for event in queue_events if event.get("event") in {"resumed", "resume"})
    return UNKNOWN


def _explicit_quality(queue_state: Mapping[str, Any], queue_events: list[Mapping[str, Any]], phase_events: list[Mapping[str, Any]]) -> str:
    values: list[Any] = []
    if "output_quality" in queue_state and queue_state.get("output_quality") is not None:
        values.append(queue_state.get("output_quality"))
    values.extend(event.get("output_quality") for event in [*queue_events, *phase_events] if "output_quality" in event)
    if not values:
        return "pending"
    quality = values[-1]
    if quality not in QUALITY_VALUES:
        raise ValueError(f"output_quality must be one of {sorted(QUALITY_VALUES)!r}: {quality!r}")
    return str(quality)


def _request_lifecycle_metrics(
    queue_state: Mapping[str, Any],
    queue_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize the optional request ledger without treating unknown as zero."""
    if "request_lifecycle" not in queue_state:
        return {
            "request_attempts": UNKNOWN,
            "artifact_record_count": UNKNOWN,
            "local_timeout_events": UNKNOWN,
            "timed_out_count": UNKNOWN,
            "pending_unknown_count": UNKNOWN,
            "authorized_recovery_count": UNKNOWN,
            "recovery_request_count": UNKNOWN,
            "automatic_retry_count": UNKNOWN,
            "known_wrapper_elapsed_ms": UNKNOWN,
            "unknown_wrapper_elapsed_count": UNKNOWN,
            "unknown_model_wait_count": UNKNOWN,
            "unknown_cost_count": UNKNOWN,
            "backend_task_id_unknown_count": UNKNOWN,
            "submission_observed_count": UNKNOWN,
        }
    records = queue_state.get("request_lifecycle")
    if not isinstance(records, list) or not all(isinstance(record, Mapping) for record in records):
        raise ValueError("request_lifecycle must be a list of objects")
    known_wrapper = [record["wrapper_elapsed_ms"] for record in records if _nonnegative_int(record.get("wrapper_elapsed_ms")) is not None]
    recovery_authorizations = queue_state.get("recovery_authorizations", [])
    if not isinstance(recovery_authorizations, list):
        raise ValueError("recovery_authorizations must be a list")
    automatic_retry_count = sum(
        1
        for event in queue_events
        if event.get("event") == "automatic_retry" or event.get("automatic_retry") is True
    ) + sum(1 for record in records if record.get("automatic_retry") is True)
    return {
        "request_attempts": len(records),
        "artifact_record_count": sum(
            1
            for record in records
            if record.get("artifact_path") not in (None, UNKNOWN)
            and isinstance(record.get("artifact_sha256"), str)
            and len(record["artifact_sha256"]) == 64
        ),
        "local_timeout_events": sum(1 for record in records if record.get("local_timeout_observed") is True),
        "timed_out_count": sum(1 for record in records if record.get("terminal_state") == "timed_out"),
        "pending_unknown_count": sum(1 for record in records if record.get("terminal_state") == "pending_unknown"),
        "authorized_recovery_count": len(recovery_authorizations),
        "recovery_request_count": sum(1 for record in records if record.get("recovery_of_request_id")),
        "automatic_retry_count": automatic_retry_count,
        "known_wrapper_elapsed_ms": sum(known_wrapper) if known_wrapper else 0,
        "unknown_wrapper_elapsed_count": sum(1 for record in records if _nonnegative_int(record.get("wrapper_elapsed_ms")) is None),
        "unknown_model_wait_count": sum(1 for record in records if record.get("model_wait_ms", UNKNOWN) == UNKNOWN),
        "unknown_cost_count": sum(1 for record in records if record.get("cost", UNKNOWN) in {UNKNOWN, "cost_unknown", None}),
        "backend_task_id_unknown_count": sum(1 for record in records if record.get("backend_task_id", UNKNOWN) == UNKNOWN),
        "submission_observed_count": sum(1 for record in records if record.get("submission_observed") is True),
    }


def summarize_production(
    queue_state: Mapping[str, Any],
    phase_events: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return stable metrics for a schema v1 queue and optional phase events.

    The function never opens output files and never mutates ``queue_state``.
    ``None`` is not used for ``output_quality``: absent review evidence is
    represented explicitly as ``"pending"``.
    """

    _require_queue_state(queue_state)
    jobs = list(queue_state["jobs"])
    queue_events = _events(queue_state.get("events", []), "queue events")
    optional_events = _events(phase_events, "phase events")
    metric_events = _merge_events(queue_events, optional_events)
    attempts = _attempt_count(jobs, metric_events)
    failures = _failure_count(jobs, metric_events)
    timestamps = _timestamp_values(queue_state, jobs, [*queue_events, *optional_events])
    span_ms: int | str = UNKNOWN
    if timestamps:
        span_ms = int((max(timestamps) - min(timestamps)).total_seconds() * 1000)

    recorded_image_elapsed = _recorded_image_elapsed(jobs, metric_events)
    image_artifact_span = _image_artifact_span_ms(queue_state, jobs, queue_events, optional_events)
    model_wait = _model_wait_ms(queue_state, jobs, queue_events, optional_events)
    image_generation_calls = _image_generation_calls(queue_state, jobs, queue_events, optional_events)
    retries = _retry_count(jobs, metric_events, attempts)
    rework_rounds = _page_rework_count(jobs, metric_events)
    failure_rate: float | str = UNKNOWN
    if isinstance(failures, int) and isinstance(attempts, int) and attempts > 0:
        failure_rate = failures / attempts

    return {
        "schema_version": SCHEMA_VERSION,
        "queue_id": queue_state.get("queue_id"),
        "wall_clock_span_ms": span_ms,
        "recorded_image_elapsed_ms": recorded_image_elapsed,
        "attempts": attempts,
        "failure_events": failures,
        "failure_rate": failure_rate,
        "retry_count": retries,
        "cache_hits": _cache_hits(jobs, metric_events),
        "page_rework_count": rework_rounds,
        "pages_completed": _pages_completed(jobs, metric_events),
        "output_quality": _explicit_quality(queue_state, queue_events, optional_events),
        # Canonical V0.11 names.  The legacy aliases above remain for
        # consumers of the preview queue format.
        "wall_clock_ms": span_ms,
        "image_artifact_span_ms": image_artifact_span,
        "model_wait_ms": model_wait,
        "image_generation_calls": image_generation_calls,
        "failures": failures,
        "retries": retries,
        "rework_rounds": rework_rounds,
        "resume_events": _resume_events(queue_state, metric_events),
        "phase_timings": summarize_phase_events(optional_events),
        "request_lifecycle": _request_lifecycle_metrics(queue_state, metric_events),
    }


def _read_json_object(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


def write_metrics_atomic(path: str | Path, metrics: Mapping[str, Any]) -> None:
    """Write metrics atomically with deterministic formatting."""

    if not isinstance(metrics, Mapping):
        raise ValueError("metrics must be a JSON object")
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(metrics, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue_json", type=Path, help="schema_version=1 queue JSON (read-only)")
    parser.add_argument("--phase-events", type=Path, help="optional phase-event JSON (read-only)")
    parser.add_argument("--output", type=Path, help="write metrics JSON atomically; otherwise print to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        queue_path = args.queue_json.resolve()
        queue_state = _read_json_object(queue_path)
        phase_path = args.phase_events.resolve() if args.phase_events else None
        phase_events = _read_json_object(phase_path) if phase_path else None
        if args.output is not None and args.output.resolve() == queue_path:
            raise ValueError("metrics output must not overwrite the queue JSON")
        if args.output is not None and phase_path is not None and args.output.resolve() == phase_path:
            raise ValueError("metrics output must not overwrite the phase-events JSON")
        metrics = summarize_production(queue_state, phase_events)
        if args.output is None:
            print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            write_metrics_atomic(args.output, metrics)
    except (OSError, ValueError) as exc:
        print(f"production_metrics: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

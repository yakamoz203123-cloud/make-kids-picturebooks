"""Build a read-only, page-oriented formal delivery review checklist."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

from project_preflight import preflight_project


PAGE_MANIFEST_RE = re.compile(r"^PAGE_MANIFEST:pages\[(?P<page>\d+)\]\.(?P<field>[^:]+):\s*(?P<detail>.*)$")
DEPENDENCY_PAGE_RE = re.compile(r"^PRODUCTION_DEPENDENCY_(?P<kind>MISSING|OUTSIDE_BOOK):page=(?P<page>\d+):field=(?P<field>[^:]+)$")

FIELD_ACTIONS = {
    "layout_design": "人工确认布局、主视觉、文字安全区和构图后，记录实际审核证据。",
    "layout_design.social_layout": "人工确认 3:4 画布、安全区和主体位置，记录实际版式证据。",
    "knowledge_check": "人工核对画面是否只表达已批准知识，并记录可见科学证据。",
    "text_image_match": "人工逐页核对正文与画面动作、阶段和角色是否一致。",
    "continuity_review": "人工与相邻页对照角色、道具、空间和科学阶段连续性。",
}

GLOBAL_ACTIONS = {
    "CONTENT_GATE": "修复故事追溯或页面 manifest 科学证据后，重新运行内容闸门；不能用人工审核记录替代内容证据。",
    "FORMAL_IMAGE_SPEC_INVALID": "保留原图，另行导出或重新生成正式 1080×1440 源图，并记录新图哈希。",
    "HUMAN_REVIEW_RECORD_MISSING": "完成页面人工审核后，保存 review 记录；脚本不能代替人工批准。",
    "STYLE_APPROVAL_NOT_LOCAL": "补充项目本地样式审批证据，或明确记录可验证的全局依赖。",
    "PROJECT_PROFILE_NOT_PRODUCTION_READY": "确认项目是否要生产；若只交付已有图片，应走 delivery-only 路径。",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _page_issue(blocker: str) -> dict[str, Any] | None:
    match = PAGE_MANIFEST_RE.match(blocker)
    if match:
        field = match.group("field").strip()
        detail = match.group("detail").strip()
        if field == "layout_design" and "social_layout.status" in detail:
            field = "layout_design.social_layout"
        return {
            "code": "PAGE_MANIFEST",
            "field": field,
            "detail": detail,
            "action": FIELD_ACTIONS.get(field, "根据预检详情完成人工审核并记录证据。"),
            "raw": blocker,
        }
    dependency = DEPENDENCY_PAGE_RE.match(blocker)
    if dependency:
        field = dependency.group("field").strip()
        kind = dependency.group("kind").lower()
        return {
            "code": f"PRODUCTION_DEPENDENCY_{dependency.group('kind')}",
            "field": field,
            "detail": f"页面依赖{('越出项目目录' if kind == 'outside_book' else '缺失')}: {field}",
            "action": "补齐该页面依赖，并重新运行 production preflight。",
            "raw": blocker,
        }
    return None


def _global_issue(blocker: str) -> dict[str, Any]:
    code, _, detail = blocker.partition(":")
    return {
        "scope": "global",
        "code": code,
        "detail": detail.strip(),
        "action": GLOBAL_ACTIONS.get(code, "根据预检详情处理该全局阻断后重新运行预检。"),
        "raw": blocker,
    }


def build_review_checklist(
    report: Mapping[str, Any],
    page_records: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Transform an existing preflight report without changing its conclusions."""

    page_records = page_records or {}
    page_issues: dict[int, list[dict[str, Any]]] = {}
    raw_global_issues: list[dict[str, Any]] = []
    for blocker in report.get("blockers", []) if isinstance(report.get("blockers"), list) else []:
        value = _text(blocker)
        issue = _page_issue(value)
        if issue is not None:
            page_match = PAGE_MANIFEST_RE.match(value) or DEPENDENCY_PAGE_RE.match(value)
            assert page_match is not None
            page_number = int(page_match.group("page"))
            page_issues.setdefault(page_number, []).append(issue)
        else:
            raw_global_issues.append(_global_issue(value))

    grouped_global: dict[str, dict[str, Any]] = {}
    for issue in raw_global_issues:
        code = str(issue["code"])
        if code not in grouped_global:
            grouped_global[code] = {
                **issue,
                "count": 0,
                "details": [],
                "occurrences": [],
            }
        grouped_global[code]["count"] += 1
        grouped_global[code]["details"].append(issue["detail"])
        grouped_global[code]["occurrences"].append(issue["raw"])
    global_issues = list(grouped_global.values())
    for issue in global_issues:
        if issue["count"] > 1:
            issue["detail"] = f"{issue['count']} 项：" + "; ".join(issue["details"])

    page_count = int(report.get("page_count") or 0)
    page_numbers = sorted(set(range(1, page_count + 1)) | set(page_records) | set(page_issues))
    pages: list[dict[str, Any]] = []
    for number in page_numbers:
        record = page_records.get(number, {})
        issues = page_issues.get(number, [])
        pages.append(
            {
                "page": number,
                "page_id": _text(record.get("page_id")) or f"PAGE-{number:02d}",
                "current_image_path": _text(record.get("current_image_path")) or None,
                "status": "needs_action" if issues else "no_machine_blocker",
                "issues": issues,
            }
        )

    warnings = [
        _text(item)
        for item in report.get("warnings", [])
        if _text(item)
    ] if isinstance(report.get("warnings"), list) else []
    closure = report.get("production_dependency_closure")
    closure = dict(closure) if isinstance(closure, Mapping) else None
    page_issue_count = sum(len(page["issues"]) for page in pages)
    return {
        "schema_version": 1,
        "status": _text(report.get("status")) or "blocked",
        "phase": _text(report.get("phase")) or "pre_delivery",
        "project_root": _text(report.get("project_root")) or None,
        "book_key": _text(report.get("book_key")) or None,
        "version": _text(report.get("version")) or None,
        "summary": {
            "page_count": len(pages),
            "pages_with_actions": sum(1 for page in pages if page["issues"]),
            "page_issue_count": page_issue_count,
            "global_issue_count": len(global_issues),
            "warning_count": len(warnings),
        },
        "pages": pages,
        "global_issues": global_issues,
        "warnings": warnings,
        "production_dependency_closure": closure,
        "automation_boundary": "此清单只整理机器预检结果，不自动把 pending 改成 passed，也不替代人工视觉、科学、连续性或发布批准。",
    }


def _markdown_text(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


def render_review_checklist_markdown(checklist: Mapping[str, Any]) -> str:
    summary = checklist.get("summary", {})
    lines = [
        "# 正式交付审核清单",
        "",
        f"- 机器预检状态：`{_markdown_text(checklist.get('status'))}`",
        f"- 项目：`{_markdown_text(checklist.get('book_key'))}` / `{_markdown_text(checklist.get('version'))}`",
        f"- 页面：{summary.get('page_count', 0)}，需要处理的页面：{summary.get('pages_with_actions', 0)}",
        f"- 页面问题：{summary.get('page_issue_count', 0)}；全局问题：{summary.get('global_issue_count', 0)}；警告：{summary.get('warning_count', 0)}",
        "",
        "> 此清单只整理机器预检结果，不自动把 pending 改成 passed，也不替代人工批准。",
        "",
        "## 页面清单",
        "",
        "| 页面 | 当前图片 | 状态 | 待处理字段 |",
        "|---|---|---|---|",
    ]
    for page in checklist.get("pages", []):
        fields = ", ".join(_markdown_text(item.get("field")) for item in page.get("issues", [])) or "无机器阻断"
        lines.append(
            f"| {_markdown_text(page.get('page_id'))} | {_markdown_text(page.get('current_image_path')) or '未声明'} | "
            f"`{_markdown_text(page.get('status'))}` | {fields} |"
        )
    lines.extend(["", "## 页面行动", ""])
    for page in checklist.get("pages", []):
        if not page.get("issues"):
            lines.append(f"### {_markdown_text(page.get('page_id'))}：无机器阻断（不等于人工通过）")
            lines.append("")
            continue
        lines.append(f"### {_markdown_text(page.get('page_id'))}")
        for issue in page.get("issues", []):
            lines.append(f"- [ ] `{_markdown_text(issue.get('field'))}`：{_markdown_text(issue.get('detail'))}")
            lines.append(f"  - 行动：{_markdown_text(issue.get('action'))}")
        lines.append("")
    lines.extend(["## 全局问题", ""])
    for issue in checklist.get("global_issues", []):
        lines.append(f"- [ ] `{_markdown_text(issue.get('code'))}`：{_markdown_text(issue.get('detail'))}")
        lines.append(f"  - 行动：{_markdown_text(issue.get('action'))}")
    if not checklist.get("global_issues"):
        lines.append("- 无")
    lines.extend(["", "## 警告", ""])
    if checklist.get("warnings"):
        lines.extend(f"- `{_markdown_text(item)}`" for item in checklist["warnings"])
    else:
        lines.append("- 无")
    lines.extend(["", "## 生产依赖闭包", ""])
    closure = checklist.get("production_dependency_closure") or {}
    lines.append(f"- 状态：`{_markdown_text(closure.get('status'))}`")
    lines.append(f"- 类型：`{_markdown_text(closure.get('profile'))}`")
    lines.append(f"- 缺失：{len(closure.get('missing', [])) if isinstance(closure.get('missing'), list) else 'unknown'}")
    lines.append(f"- 越界：{len(closure.get('outside_book', [])) if isinstance(closure.get('outside_book'), list) else 'unknown'}")
    lines.extend(["", "## 自动化边界", "", f"> {_markdown_text(checklist.get('automation_boundary'))}", ""])
    return "\n".join(lines)


def write_review_checklist(checklist: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "review-checklist.json"
    markdown_path = output_root / "review-checklist.md"
    if json_path.exists() or markdown_path.exists():
        raise FileExistsError(f"review checklist output already exists: {output_root}")
    json_path.write_text(json.dumps(checklist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_review_checklist_markdown(checklist), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def ensure_output_outside_project(project_root: str | Path | None, output_dir: str | Path) -> None:
    """Reject checklist output paths that would mutate the inspected project."""

    if not project_root:
        return
    root = Path(project_root).resolve()
    output = Path(output_dir).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        return
    raise ValueError(f"review checklist output must be outside project root: {output}")


def _load_page_records(project_root: str | Path, book_key: str | None, version: str | None) -> dict[int, dict[str, Any]]:
    if not project_root or not book_key or not version:
        return {}
    root = Path(project_root)
    book_dir = root / "books" / book_key / version
    candidates = [book_dir / "page-manifest.json", book_dir / "content" / "page-manifest.json"]
    manifest_path = next((path for path in candidates if path.is_file()), None)
    if manifest_path is None:
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    pages = data.get("pages") if isinstance(data, Mapping) else None
    if not isinstance(pages, list):
        return {}
    return {
        int(page["page"]): {
            "page_id": page.get("page_id"),
            "current_image_path": page.get("current_image_path"),
        }
        for page in pages
        if isinstance(page, Mapping) and str(page.get("page", "")).isdigit()
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("book_id")
    parser.add_argument("--version")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = preflight_project(
        args.project,
        args.book_id,
        version=args.version,
        phase="pre_delivery",
        mode="report-only",
    )
    ensure_output_outside_project(report.get("project_root"), args.output_dir)
    records = _load_page_records(report.get("project_root"), report.get("book_key"), report.get("version"))
    checklist = build_review_checklist(report, records)
    paths = write_review_checklist(checklist, args.output_dir)
    print(json.dumps({"status": checklist["status"], **paths}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

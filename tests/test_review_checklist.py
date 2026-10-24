from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from review_checklist import (  # noqa: E402
    build_review_checklist,
    render_review_checklist_markdown,
    ensure_output_outside_project,
    main,
    write_review_checklist,
)


def _report() -> dict:
    return {
        "schema_version": 1,
        "status": "blocked",
        "phase": "pre_delivery",
        "project_root": "C:/projects/bean-book",
        "book_key": "bean-book",
        "version": "v1",
        "page_count": 3,
        "blockers": [
            "PAGE_MANIFEST:pages[1].layout_design: 完成模式要求layout_design.status为passed",
            "PAGE_MANIFEST:pages[1].layout_design: 完成模式要求social_layout.status为passed",
            "PAGE_MANIFEST:pages[2].knowledge_check: completion requires passed status and actual evidence",
            "FORMAL_IMAGE_SPEC_INVALID:1:1086x1448:RGB",
            "FORMAL_IMAGE_SPEC_INVALID:2:1086x1448:RGB",
        ],
        "warnings": [
            "STYLE_APPROVAL_NOT_LOCAL:STYLE-CORE-01:v1.2",
            "HUMAN_REVIEW_RECORD_MISSING",
        ],
        "production_dependency_closure": {
            "status": "passed",
            "profile": "production-ready",
            "missing": [],
            "outside_book": [],
        },
    }


def _page_records() -> dict[int, dict[str, str]]:
    return {
        1: {"page_id": "PAGE-01", "current_image_path": "native/page|01.png"},
        2: {"page_id": "PAGE-02", "current_image_path": "native/page-02.png"},
        3: {"page_id": "PAGE-03", "current_image_path": "native/page-03.png"},
    }


def test_build_review_checklist_groups_page_fields_and_keeps_full_names() -> None:
    checklist = build_review_checklist(_report(), _page_records())

    assert checklist["summary"] == {
        "page_count": 3,
        "pages_with_actions": 2,
        "page_issue_count": 3,
        "global_issue_count": 1,
        "warning_count": 2,
    }
    assert checklist["pages"][0]["page_id"] == "PAGE-01"
    assert checklist["pages"][0]["status"] == "needs_action"
    assert [item["field"] for item in checklist["pages"][0]["issues"]] == [
        "layout_design",
        "layout_design.social_layout",
    ]
    assert checklist["pages"][1]["issues"][0]["field"] == "knowledge_check"
    assert checklist["pages"][2]["status"] == "no_machine_blocker"


def test_build_review_checklist_keeps_global_issues_and_warnings_separate() -> None:
    checklist = build_review_checklist(_report(), _page_records())

    assert checklist["global_issues"][0]["code"] == "FORMAL_IMAGE_SPEC_INVALID"
    assert checklist["global_issues"][0]["scope"] == "global"
    assert checklist["global_issues"][0]["count"] == 2
    assert checklist["warnings"] == [
        "STYLE_APPROVAL_NOT_LOCAL:STYLE-CORE-01:v1.2",
        "HUMAN_REVIEW_RECORD_MISSING",
    ]
    assert checklist["production_dependency_closure"]["missing"] == []


def test_build_review_checklist_exposes_content_gate_blocker() -> None:
    report = _report()
    report["blockers"].append("CONTENT_GATE:manifest:missing_storyboard_science_review")

    checklist = build_review_checklist(report, _page_records())

    issue = next(item for item in checklist["global_issues"] if item["code"] == "CONTENT_GATE")
    assert "missing_storyboard_science_review" in issue["detail"]


def test_render_markdown_is_actionable_without_claiming_human_approval() -> None:
    markdown = render_review_checklist_markdown(build_review_checklist(_report(), _page_records()))

    assert "人工确认" in markdown
    assert "layout_design.social_layout" in markdown
    assert "native/page\\|01.png" in markdown
    assert "不自动把 pending 改成 passed" in markdown
    assert "PAGE-03" in markdown


def test_write_review_checklist_does_not_overwrite_existing_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "review-checklist"
    checklist = build_review_checklist(_report(), _page_records())

    paths = write_review_checklist(checklist, output_dir)
    assert set(paths) == {"json", "markdown"}
    assert json.loads(Path(paths["json"]).read_text(encoding="utf-8"))["schema_version"] == 1
    assert Path(paths["markdown"]).is_file()

    with pytest.raises(FileExistsError):
        write_review_checklist(checklist, output_dir)


def test_output_directory_must_be_outside_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    with pytest.raises(ValueError, match="outside project root"):
        ensure_output_outside_project(project_root, project_root / "reports")


def test_blocked_review_checklist_cli_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("review_checklist.preflight_project", lambda *args, **kwargs: _report())
    output_dir = tmp_path / "review-checklist"

    assert main(["ignored-project", "b01", "--version", "v1", "--output-dir", str(output_dir)]) == 2

import json
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import workflow
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def passed_report() -> dict:
    return {
        "status": "passed",
        "phase": "pre_generation",
        "mode": "strict",
        "project_root": "C:/project",
        "book_key": "b02",
        "version": "v1",
        "page_count": 12,
        "plan_fingerprint": "plan-123",
        "blockers": [],
        "warnings": [],
        "image_model_calls": 0,
        "write_operations": 0,
        "passed": [
            {"check": "approved_asset_and_style_references"},
            {"check": "production_dependency_closure"},
            {"check": "research_traceability"},
            {"check": "content_gate"},
            {"check": "page_numbers_match"},
            {"check": "page_text_matches_storyboard"},
            {"check": "page_manifest_validation"},
        ],
    }


def test_doctor_summary_exposes_compact_gates_and_authorization_boundary() -> None:
    result = workflow._doctor_summary(passed_report(), elapsed_ms=17)

    assert result["status"] == "passed"
    assert result["elapsed_ms"] == 17
    assert result["gate_summary"] == {
        "assets": "passed",
        "content": "passed",
        "storyboard": "passed",
        "pages": "passed",
    }
    assert result["input_snapshot"] == {
        "status": "stable",
        "plan_fingerprint": "plan-123",
    }
    assert result["generation_authorization"] == "READY_FOR_USER_AUTHORIZATION"
    assert result["image_generation"] == "SKIPPED"


def test_doctor_summary_holds_on_blockers() -> None:
    report = passed_report()
    report["status"] = "blocked"
    report["blockers"] = ["CONTENT_GATE_FAILED"]
    report["passed"] = []

    result = workflow._doctor_summary(report, elapsed_ms=3)

    assert result["generation_authorization"] == "HOLD"
    assert result["input_snapshot"]["status"] == "unstable"
    assert all(value == "hold" for value in result["gate_summary"].values())
    assert result["blockers"] == ["CONTENT_GATE_FAILED"]


def test_doctor_can_write_full_report_without_printing_it(monkeypatch, tmp_path: Path) -> None:
    report = passed_report()

    def fake_preflight(*args, **kwargs):
        return report

    monkeypatch.setattr(workflow, "preflight_project", fake_preflight)
    output = tmp_path / "review" / "preflight.json"

    result = workflow.doctor(
        "C:/project",
        "b02",
        version="v1",
        report_json=output,
    )

    assert result["report_path"] == str(output.resolve())
    assert json.loads(output.read_text(encoding="utf-8")) == report

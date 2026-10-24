import sys
from pathlib import Path
from unittest.mock import patch

import pytest


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import generation_queue
    import project_preflight
    from project_preflight import preflight_project
    from test_phase3_preflight_archive import _fixture
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def _production_paths(root: Path) -> tuple[Path, Path]:
    book = root / "books" / "b01" / "v1"
    return book, root / "books" / "b01" / "v1" / "generation-queue.json"


def test_preflight_uses_supplied_plan_without_rebuilding_it(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, _queue = _production_paths(root)
    planned = generation_queue._plan(book)

    with patch.object(project_preflight, "_plan", side_effect=AssertionError("plan rebuilt")):
        result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict", planned=planned)

    assert result["status"] == "passed"
    assert result["plan_fingerprint"] == planned["plan_fingerprint"]


def test_preflight_report_contains_reusable_input_fingerprints(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, _queue = _production_paths(root)
    planned = generation_queue._plan(book)

    result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict", planned=planned)

    assert result["status"] == "passed"
    assert result["preflight_input_fingerprint"]
    assert result["global_input_fingerprint"]
    assert result["preflight_input_snapshot"]


def test_changed_research_evidence_invalidates_preflight_receipt(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, _queue = _production_paths(root)
    planned = generation_queue._plan(book)
    result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict", planned=planned)
    receipt = {
        "schema_version": 1,
        "status": "passed",
        "mode": "production",
        "phase": "pre_generation",
        "project_root": str(root.resolve()),
        "book_key": "b01",
        "version": "v1",
        "plan_fingerprint": result["plan_fingerprint"],
        "workflow_rules_version": result["workflow_rules_version"],
        "preflight_input_fingerprint": result["preflight_input_fingerprint"],
        "global_input_fingerprint": result["global_input_fingerprint"],
        "preflight_input_snapshot": result["preflight_input_snapshot"],
    }

    assert project_preflight._is_preflight_receipt_reusable(root, "b01", "v1", planned, receipt)

    whitelist = book / "review" / "knowledge-whitelist.json"
    whitelist.write_text("{\"changed\": true}\n", encoding="utf-8")

    assert not project_preflight._is_preflight_receipt_reusable(root, "b01", "v1", planned, receipt)

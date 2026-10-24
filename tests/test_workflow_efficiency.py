import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
for _module_name in ("generation_queue", "project_preflight"):
    sys.modules.pop(_module_name, None)
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


def test_queue_init_passes_one_plan_to_preflight(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, queue = _production_paths(root)

    with patch.object(project_preflight, "_plan", side_effect=AssertionError("plan rebuilt")):
        state = generation_queue.init_queue(book, queue)

    assert state["workflow_gate"]["status"] == "passed"
    assert state["page_count"] == 1


def test_queue_init_holds_mutation_lock_while_building_gate(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, queue = _production_paths(root)
    lock_active = False
    original_gate = generation_queue._pre_generation_gate

    class ProbeLock:
        def __enter__(self):
            nonlocal lock_active
            lock_active = True
            return self

        def __exit__(self, exc_type, exc, tb):
            nonlocal lock_active
            lock_active = False

    def gate_probe(*args, **kwargs):
        assert lock_active is True
        return original_gate(*args, **kwargs)

    with patch.object(generation_queue, "_queue_mutation_lock", return_value=ProbeLock()):
        with patch.object(generation_queue, "_pre_generation_gate", side_effect=gate_probe):
            generation_queue.init_queue(book, queue)


def test_queue_reinitialization_reuses_valid_preflight_receipt(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, queue = _production_paths(root)
    first = generation_queue.init_queue(book, queue)

    with patch.object(project_preflight, "preflight_project", side_effect=AssertionError("full preflight rerun")):
        second = generation_queue.init_queue(book, queue)

    assert second["workflow_gate"] == first["workflow_gate"]
    assert second["preflight_receipt"] == first["preflight_receipt"]


def test_authorization_records_page_request_fingerprints(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, queue = _production_paths(root)
    state = generation_queue.init_queue(book, queue)

    authorization = generation_queue.authorize_generation(
        queue,
        approval="测试授权",
        max_calls=1,
    )

    assert authorization["page_fingerprints"] == {
        "1": state["jobs"][0]["request_fingerprint"],
    }


def test_reconcile_page_scoped_authorization_keeps_only_unchanged_pages() -> None:
    authorizations = [
        {
            "authorization_id": "auth-1",
            "max_calls": 2,
            "used_calls": 0,
            "page_fingerprints": {"1": "old-page-1", "2": "same-page-2"},
        }
    ]
    jobs = [
        {"page": 1, "request_fingerprint": "new-page-1"},
        {"page": 2, "request_fingerprint": "same-page-2"},
    ]

    reconciled = generation_queue._reconcile_generation_authorizations(
        authorizations,
        jobs,
        plan_changed=True,
        global_input_changed=False,
    )

    assert reconciled[0]["page_fingerprints"] == {"2": "same-page-2"}


def test_global_input_change_clears_page_scoped_authorization() -> None:
    authorizations = [
        {
            "authorization_id": "auth-1",
            "max_calls": 2,
            "used_calls": 0,
            "page_fingerprints": {"1": "same-page-1"},
        }
    ]

    assert generation_queue._reconcile_generation_authorizations(
        authorizations,
        [{"page": 1, "request_fingerprint": "same-page-1"}],
        plan_changed=True,
        global_input_changed=True,
    ) == []


def test_page_scoped_authorization_rejects_changed_page() -> None:
    state = {
        "requires_user_authorization": True,
        "generation_authorizations": [
            {
                "authorization_id": "auth-1",
                "max_calls": 2,
                "used_calls": 0,
                "page_fingerprints": {"1": "old-page-1", "2": "same-page-2"},
            }
        ],
        "jobs": [
            {"page": 1, "request_fingerprint": "new-page-1"},
            {"page": 2, "request_fingerprint": "same-page-2"},
        ],
    }

    with pytest.raises(PermissionError, match="stale"):
        generation_queue._generation_authorization(state, "auth-1", 1, pages=[1])

    assert generation_queue._generation_authorization(state, "auth-1", 1, pages=[2])["authorization_id"] == "auth-1"


def test_queue_reinitialization_preserves_unaffected_page_authorization(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    book, queue = _production_paths(root)
    content = book / "content"
    prompt_two = content / "prompts" / "page-02.md"
    prompt_two.write_text("第二页提示词\n", encoding="utf-8")

    for filename in ("page-manifest.json", "storyboard.json"):
        path = content / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        page_two = copy.deepcopy(document["pages"][0])
        page_two["page"] = 2
        page_two["page_id"] = "PAGE-02"
        page_two["page_version"] = "PAGE-02-v1"
        page_two["text"] = "小熊继续观察第二页。"
        page_two["current_prompt_path"] = "prompts/page-02.md"
        page_two["previous_page_state"] = {"state_id": "page_two", "summary": "进入第二页。"}
        page_two["current_page_entry"] = {"state_id": "page_two", "summary": "小熊继续观察。"}
        page_two["next_page_hook"] = {"state_id": "story_end", "summary": "故事结束。"}
        document["pages"][0]["next_page_hook"] = {"state_id": "page_two", "summary": "进入第二页。"}
        document["pages"].append(page_two)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    layout_path = content / "layout.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["pages"].append({"page": 2, "style_version": "v0.1"})
    layout_path.write_text(json.dumps(layout, ensure_ascii=False), encoding="utf-8")
    page_text_path = content / "page-text.json"
    page_text = json.loads(page_text_path.read_text(encoding="utf-8"))
    page_text["pages"].append({"page": 2, "text": "小熊继续观察第二页。"})
    page_text_path.write_text(json.dumps(page_text, ensure_ascii=False), encoding="utf-8")

    first = generation_queue.init_queue(book, queue)
    authorization = generation_queue.authorize_generation(queue, approval="测试授权", max_calls=2)

    manifest_path = content / "page-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][1]["page_version"] = "PAGE-02-v2"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    second = generation_queue.init_queue(book, queue)
    preserved = second["generation_authorizations"][0]
    assert preserved["authorization_id"] == authorization["authorization_id"]
    assert preserved["page_fingerprints"] == {"1": first["jobs"][0]["request_fingerprint"]}

    generation_queue.claim_job(queue, 1, authorization_id=authorization["authorization_id"])
    with pytest.raises(PermissionError, match="stale"):
        generation_queue.claim_job(queue, 2, authorization_id=authorization["authorization_id"])

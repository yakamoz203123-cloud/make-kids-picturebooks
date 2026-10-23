import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "generation_queue.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generation_queue_lifecycle_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT_PATH.parent))
    return module


def make_book(root: Path) -> tuple[Path, Path]:
    book = root / "book"
    (book / "prompts").mkdir(parents=True)
    (book / "characters" / "v1").mkdir(parents=True)
    (book / "characters" / "v1" / "production-reference.png").write_bytes(b"reference")
    (book / "story.md").write_text("第一页：孩子观察一片叶子。\n", encoding="utf-8")
    page = {
        "page": 1,
        "page_id": "PAGE-01",
        "page_version": "PAGE-01-v1",
        "text_version": "v1",
        "characters_version": "v1",
        "character_reference_path": "characters/v1/production-reference.png",
        "production_reference_path": "characters/v1/production-reference.png",
        "current_prompt_path": "prompts/page-01.md",
        "current_image_path": None,
        "story_dependency": {"lines": [1, 1]},
    }
    (book / "prompts" / "page-01.md").write_text("一片叶子", encoding="utf-8")
    (book / "page-manifest.json").write_text(json.dumps({"title": "测试", "age_band": "3-4", "pages": [page]}), encoding="utf-8")
    (book / "storyboard.json").write_text(json.dumps({"pages": [page]}), encoding="utf-8")
    (book / "layout.json").write_text(json.dumps({"pages": [{**page, "source_aspect_ratio": "1:1"}]}), encoding="utf-8")
    return book, root / "queue.json"


def write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1024, 1024), (20, 80, 120)).save(path, format="PNG")


def request_record(queue_path: Path, request_id: str) -> dict:
    state = json.loads(queue_path.read_text(encoding="utf-8"))
    return next(item for item in state["request_lifecycle"] if item["request_id"] == request_id)


def test_success_request_records_artifact_and_unknown_server_fields(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)

    claimed = module.claim_job(queue, 1)
    request_id = claimed["current_request_id"]
    module.mark_request_submitted(queue, request_id)
    output = book / "images" / "page-01.png"
    write_image(output)
    module.complete_job(queue, 1, output, elapsed_ms=1250)

    record = request_record(queue, request_id)
    assert record["page_id"] == "PAGE-01"
    assert record["page_version"] == "PAGE-01-v1"
    assert record["revision"] == 1
    assert record["attempt"] == 1
    assert record["submission_observed"] is True
    assert record["backend_task_id"] == "unknown"
    assert record["terminal_state"] == "succeeded"
    assert record["artifact_path"] == "images/page-01.png"
    assert len(record["artifact_sha256"]) == 64
    assert record["wrapper_elapsed_ms"] == 1250
    assert record["model_wait_ms"] == "unknown"
    assert record["cost"] == "cost_unknown"


def test_new_request_requires_observed_submission_before_completion(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    output = book / "images" / "page-01.png"
    write_image(output)

    with pytest.raises(ValueError, match="REQUEST_SUBMISSION_NOT_OBSERVED"):
        module.complete_job(queue, 1, output)

    state = json.loads(queue.read_text(encoding="utf-8"))
    job = state["jobs"][0]
    record = request_record(queue, claimed["current_request_id"])
    assert job["status"] == "running"
    assert record["terminal_state"] == "running"
    assert record["artifact_path"] is None
    assert record["artifact_sha256"] is None


def test_new_request_cannot_hide_lifecycle_record_as_legacy(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    output = book / "images" / "page-01.png"
    write_image(output)
    state = json.loads(queue.read_text(encoding="utf-8"))
    state.pop("request_lifecycle", None)
    queue.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="REQUEST_LIFECYCLE_RECORD_MISSING"):
        module.complete_job(queue, 1, output)

    state_after = json.loads(queue.read_text(encoding="utf-8"))
    assert state_after["jobs"][0]["status"] == "running"
    assert state_after["jobs"][0]["current_request_id"] == claimed["current_request_id"]


def test_legacy_running_job_without_lifecycle_remains_completeable(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    state = module.init_queue(book, queue)
    state.pop("request_lifecycle", None)
    job = state["jobs"][0]
    job["status"] = "running"
    job["attempts"] = 1
    job["started_at"] = "2026-10-21T00:00:00+00:00"
    queue.write_text(json.dumps(state), encoding="utf-8")
    output = book / "images" / "page-01.png"
    write_image(output)

    completed = module.complete_job(queue, 1, output)

    assert completed["status"] == "completed"
    assert json.loads(queue.read_text(encoding="utf-8"))["jobs"][0]["status"] == "completed"


def test_resume_does_not_requeue_submitted_request_as_an_approved_retry(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    module.mark_request_submitted(queue, claimed["current_request_id"])

    state = module.resume_queue(queue)

    assert state["jobs"][0]["status"] == "failed"
    assert request_record(queue, claimed["current_request_id"])["terminal_state"] == "pending_unknown"
    with pytest.raises(RuntimeError, match="unknown"):
        module.claim_job(queue, 1)


def test_reset_does_not_bypass_authorized_recovery_for_unknown_request(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    module.mark_request_pending_unknown(queue, claimed["current_request_id"])
    before = queue.read_bytes()

    with pytest.raises(PermissionError, match="authorization"):
        module.reset_page(queue, 1, "attempted unknown request reset")

    assert queue.read_bytes() == before
    with pytest.raises(RuntimeError, match="unknown"):
        module.claim_job(queue, 1)


def test_completion_rejects_request_identity_mismatch_before_writing_success(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    module.mark_request_submitted(queue, claimed["current_request_id"])
    output = book / "images" / "page-01.png"
    write_image(output)
    state = json.loads(queue.read_text(encoding="utf-8"))
    state["jobs"][0]["revision"] = 2
    queue.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="REQUEST_LIFECYCLE_IDENTITY_MISMATCH"):
        module.complete_job(queue, 1, output)

    state_after = json.loads(queue.read_text(encoding="utf-8"))
    assert state_after["jobs"][0]["status"] == "running"
    assert request_record(queue, claimed["current_request_id"])["terminal_state"] == "running"


def test_local_timeout_becomes_pending_unknown_without_retry(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue, max_attempts=2)
    claimed = module.claim_job(queue, 1)

    module.mark_request_timeout(queue, claimed["current_request_id"], wrapper_elapsed_ms=5000)
    assert request_record(queue, claimed["current_request_id"])["terminal_state"] == "timed_out"
    module.mark_request_pending_unknown(queue, claimed["current_request_id"])
    record = request_record(queue, claimed["current_request_id"])
    state = json.loads(queue.read_text(encoding="utf-8"))

    assert record["terminal_state"] == "pending_unknown"
    assert record["backend_task_id"] == "unknown"
    assert record["model_wait_ms"] == "unknown"
    assert record["cost"] == "cost_unknown"
    assert state["jobs"][0]["status"] == "failed"  # legacy queue compatibility
    with pytest.raises(RuntimeError, match="unknown"):
        module.claim_job(queue, 1)
    assert len(state["request_lifecycle"]) == 1


def test_authorized_recovery_creates_new_request_and_keeps_candidate_separate(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    original = module.claim_job(queue, 1)["current_request_id"]
    module.mark_request_pending_unknown(queue, original)
    approval = module.authorize_page_recovery(queue, 1, original, approval="user-approved")
    recovered = module.claim_page_recovery(queue, 1, original)

    assert recovered["current_request_id"] != original
    assert recovered["revision"] == 2
    assert recovered["recovery_of_request_id"] == original
    assert recovered["recovery_approval"] == approval["approval"]
    assert recovered["output_path"] == "images/page-01-r2.png"
    assert recovered["output_path"] != "images/page-01.png"

    output = book / recovered["output_path"]
    write_image(output)
    module.mark_request_submitted(queue, recovered["current_request_id"])
    module.complete_job(queue, 1, output, elapsed_ms=700)
    state = json.loads(queue.read_text(encoding="utf-8"))
    assert len(state["request_lifecycle"]) == 2
    assert request_record(queue, recovered["current_request_id"])["terminal_state"] == "succeeded"
    assert (book / "images" / "page-01.png").exists() is False


def test_recovery_without_authorization_is_rejected_and_does_not_create_request(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    original = module.claim_job(queue, 1)["current_request_id"]
    module.mark_request_pending_unknown(queue, original)

    with pytest.raises(PermissionError, match="authorization"):
        module.claim_page_recovery(queue, 1, original)
    state = json.loads(queue.read_text(encoding="utf-8"))
    assert len(state["request_lifecycle"]) == 1


def test_recovery_authorization_is_single_use_and_duplicate_completion_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    original = module.claim_job(queue, 1)["current_request_id"]
    module.mark_request_pending_unknown(queue, original)
    module.authorize_page_recovery(queue, 1, original, approval="user-approved")
    recovered = module.claim_page_recovery(queue, 1, original)

    with pytest.raises(PermissionError, match="used"):
        module.claim_page_recovery(queue, 1, original)
    output = book / recovered["output_path"]
    write_image(output)
    module.mark_request_submitted(queue, recovered["current_request_id"])
    module.complete_job(queue, 1, output)
    with pytest.raises(RuntimeError, match="running"):
        module.complete_job(queue, 1, output)


def test_duplicate_submission_is_idempotent_but_conflicting_backend_id_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    request_id = module.claim_job(queue, 1)["current_request_id"]

    first = module.mark_request_submitted(queue, request_id, backend_task_id="backend-1")
    second = module.mark_request_submitted(queue, request_id, backend_task_id="backend-1")
    assert first == second
    with pytest.raises(ValueError, match="backend_task_id"):
        module.mark_request_submitted(queue, request_id, backend_task_id="backend-2")


def test_batch_claim_creates_one_lifecycle_request_without_double_claim_event(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)

    claimed = module.claim_batch(queue, [1])
    state = json.loads(queue.read_text(encoding="utf-8"))
    assert claimed[0]["current_request_id"]
    assert len(state["request_lifecycle"]) == 1
    assert sum(1 for event in state["events"] if event["event"] == "claimed") == 0
    assert sum(1 for event in state["events"] if event["event"] == "batch_claimed") == 1


def test_lifecycle_validation_rejects_bad_identity_missing_artifact_and_changed_hash(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    request_id = claimed["current_request_id"]
    record = request_record(queue, request_id)

    with pytest.raises(ValueError, match="request_id"):
        module.validate_request_lifecycle_record({**record, "request_id": ""})
    with pytest.raises(ValueError, match="page_version"):
        module.validate_request_lifecycle_record({**record, "page_version": "PAGE-01-v9"}, expected_page_version="PAGE-01-v1")
    with pytest.raises(ValueError, match="artifact"):
        module.validate_request_lifecycle_record({**record, "artifact_path": "images/missing.png", "artifact_sha256": "0" * 64}, book_dir=book)
    write_image(book / "images" / "page-01.png")
    with pytest.raises(ValueError, match="SHA-256"):
        module.validate_request_lifecycle_record({**record, "artifact_path": "images/page-01.png", "artifact_sha256": "0" * 64}, book_dir=book)


def test_legacy_queue_without_lifecycle_fields_remains_readable(tmp_path: Path) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    state = module.init_queue(book, queue)
    state.pop("request_lifecycle", None)
    queue.write_text(json.dumps(state), encoding="utf-8")

    loaded = module.status(queue)
    assert loaded["page_count"] == 1
    claimed = module.claim_job(queue, 1)
    assert claimed["current_request_id"]
    assert request_record(queue, claimed["current_request_id"])["backend_task_id"] == "unknown"


def test_atomic_lifecycle_update_preserves_queue_when_write_is_interrupted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    book, queue = make_book(tmp_path)
    module.init_queue(book, queue)
    claimed = module.claim_job(queue, 1)
    before = queue.read_bytes()

    def interrupted_write(path, value):
        raise OSError("simulated interruption")

    monkeypatch.setattr(module, "_write_atomic", interrupted_write)
    with pytest.raises(OSError, match="interruption"):
        module.mark_request_submitted(queue, claimed["current_request_id"], backend_task_id="backend-1")
    assert queue.read_bytes() == before

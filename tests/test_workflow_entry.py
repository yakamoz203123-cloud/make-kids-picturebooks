from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
for _module_name in (
    "workflow",
    "generation_queue",
    "project_preflight",
    "release_pure_image_delivery",
):
    sys.modules.pop(_module_name, None)
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import workflow
    from build_pure_image_delivery import build_delivery
    from test_phase3_preflight_archive import _fixture
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def _book(root: Path) -> Path:
    return root / "books" / "b01" / "v1"


def test_doctor_returns_compact_strict_summary_without_creating_queue(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    result = workflow.doctor(root, "b01", version="v1")

    assert result["status"] == "passed"
    assert result["page_count"] == 1
    assert result["blockers"] == []
    assert result["image_model_calls"] == 0
    assert result["write_operations"] == 0
    assert not (_book(root) / "review" / "production-queue.json").exists()


def test_resume_without_approval_stops_before_claiming(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    result = workflow.resume(root, "b01", version="v1")

    assert result["status"] == "authorization_required"
    assert result["next_page"] == 1
    state = json.loads(Path(result["queue_path"]).read_text(encoding="utf-8"))
    assert state["jobs"][0]["status"] == "pending"


def test_resume_with_approval_claims_one_page_and_keeps_serial_mode(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    result = workflow.resume(
        root,
        "b01",
        version="v1",
        approval="用户批准继续生成下一页",
        max_calls=1,
    )

    assert result["status"] == "claimed"
    assert result["page"] == 1
    assert result["job"]["status"] == "running"
    state = json.loads(Path(result["queue_path"]).read_text(encoding="utf-8"))
    assert state["max_in_flight"] == 1
    assert state["generation_authorizations"][0]["used_calls"] == 1


def test_resume_reports_waiting_when_a_page_is_already_running(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    first = workflow.resume(root, "b01", version="v1", approval="批准一页", max_calls=1)

    result = workflow.resume(root, "b01", version="v1")

    assert first["status"] == "claimed"
    assert result["status"] == "waiting"
    assert result["running_pages"] == [1]


def test_finish_page_completes_claimed_page_and_publishes_manifest_path(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    claimed = workflow.resume(root, "b01", version="v1", approval="批准一页", max_calls=1)
    book = _book(root)
    output = book / "images" / "page-01.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1080, 1440), (220, 180, 120)).save(output, format="PNG")

    result = workflow.finish_page(
        root,
        "b01",
        1,
        "images/page-01.png",
        version="v1",
        backend_task_id="backend-page-01",
        elapsed_ms=100,
    )

    assert claimed["status"] == "claimed"
    assert result["status"] == "completed"
    manifest = json.loads((book / "content" / "page-manifest.json").read_text(encoding="utf-8"))
    assert manifest["pages"][0]["current_image_path"] == "images/page-01.png"


def test_finished_page_flows_directly_into_delivery_without_path_bridge(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    workflow.resume(root, "b01", version="v1", approval="批准一页", max_calls=1)
    book = _book(root)
    output = book / "images" / "page-01.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1080, 1440), (220, 180, 120)).save(output, format="PNG")

    workflow.finish_page(
        root,
        "b01",
        1,
        "images/page-01.png",
        version="v1",
        backend_task_id="backend-page-01",
        elapsed_ms=100,
    )

    delivery = book / "delivery" / "pure-image-delivery-v1"
    result = build_delivery(root, "b01", delivery, version="v1")

    assert result["status"] == "built"
    assert (delivery / "images" / "page-01.png").is_file()


def test_resume_reports_complete_for_cached_project(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    book = _book(root)
    (book / "images").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(book / "content" / "images" / "page-01.png", book / "images" / "page-01.png")

    result = workflow.resume(root, "b01", version="v1")

    assert result["status"] == "complete"
    assert result["counts"]["cached"] == 1
    assert result["generation_status"] == "generated"
    assert result["review_status"] == "approved"
    assert result["next_gate"] == "delivery"


def test_deliver_delegates_to_existing_release_gate(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    delivery = _book(root) / "delivery" / "pure-image-delivery-v1"
    expected = {"status": "released", "output": str(delivery)}

    with patch.object(workflow, "release_delivery", return_value=expected) as release:
        result = workflow.deliver(root, "b01", delivery, version="v1")

    assert result == expected
    release.assert_called_once_with(root, "b01", delivery, version="v1")


def test_cli_returns_machine_readable_status_for_missing_approval(tmp_path: Path, capsys) -> None:
    root = _fixture(tmp_path)

    exit_code = workflow.main(["resume", str(root), "b01", "--version", "v1"])

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "authorization_required"

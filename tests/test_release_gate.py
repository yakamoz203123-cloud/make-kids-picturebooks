from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from release_pure_image_delivery import DeliveryReleaseError, release_delivery
    from test_phase3_preflight_archive import _fixture
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def test_release_requires_pre_delivery_gate_and_writes_one_receipt(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    delivery = root / "books" / "b01" / "v1" / "delivery" / "pure-image-delivery-v1"

    result = release_delivery(root, "b01", delivery, version="v1")

    assert result["status"] == "released"
    validation = json.loads((delivery / "delivery-validation.json").read_text(encoding="utf-8"))
    assert validation["release_status"] == "human_review_pending"
    receipt = json.loads((delivery / "release-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "released"
    assert receipt["preflight_status"] == "passed"


def test_release_is_blocked_when_human_review_record_is_missing(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    delivery = root / "books" / "b01" / "v1" / "delivery" / "pure-image-delivery-v1"
    (root / "books" / "b01" / "v1" / "review" / "review.json").unlink()

    with pytest.raises(DeliveryReleaseError, match="PRE_DELIVERY_GATE_BLOCKED"):
        release_delivery(root, "b01", delivery, version="v1")
    assert not (delivery / "release-receipt.json").exists()


def test_existing_release_receipt_is_revalidated_after_input_change(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    delivery = root / "books" / "b01" / "v1" / "delivery" / "pure-image-delivery-v1"
    release_delivery(root, "b01", delivery, version="v1")

    manifest_path = root / "books" / "b01" / "v1" / "content" / "page-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["science_visual_consistency"]["checks"].append("workflow-revalidation")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DeliveryReleaseError, match="PRE_DELIVERY_GATE_BLOCKED"):
        release_delivery(root, "b01", delivery, version="v1")

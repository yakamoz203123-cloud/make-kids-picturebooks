import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from build_pure_image_delivery import DeliveryError, build_delivery
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _make_page(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG", optimize=False)


def _fixture(tmp_path: Path, *, include_page_03: bool = True) -> Path:
    root = tmp_path / "project"
    book = root / "books" / "b01" / "v0.1"
    _write_json(
        root / "project.json",
        {
            "schema_version": 1,
            "title": "测试自然朋友",
            "target_age_bands": ["3-4"],
            "books": [{"id": "b01", "title": "测试自然朋友"}],
        },
    )
    _write_json(
        book / "storyboard.json",
        {
            "schema_version": 1,
            "book_id": "b01",
            "version": "v0.1",
            "title": "测试自然朋友",
            "age_band": "3-4",
            "pages": [
                {"page": 1, "page_id": "PAGE-01", "kind": "cover", "text": "测试自然朋友"},
                {
                    "page": 2,
                    "page_id": "PAGE-02",
                    "page_version": "PAGE-02-v0.1",
                    "kind": "story",
                    "text": "小熊看见一片叶子。",
                },
                {
                    "page": 3,
                    "page_id": "PAGE-03",
                    "page_version": "PAGE-03-v0.1",
                    "kind": "closing",
                    "text": "小猛说：下次再找朋友。",
                },
            ],
        },
    )
    _make_page(book / "images" / "pages" / "page-02-v0.1.png", (1086, 1448), (255, 230, 160))
    if include_page_03:
        _make_page(book / "images" / "pages" / "page-03-v0.1.png", (1080, 1440), (160, 220, 180))
    return root


def test_builds_deterministic_pure_image_package_from_storyboard(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    output = tmp_path / "delivery-v1"

    result = build_delivery(root, "b01", output)

    assert result["status"] == "built"
    assert result["output_mode"] == "pure-images"
    assert result["model_generation_calls"] == 0
    assert result["page_count"] == 2
    assert (output / "images" / "page-02.png").is_file()
    assert (output / "images" / "page-03.png").is_file()
    assert (output / "text" / "page-02.txt").read_text(encoding="utf-8") == "小熊看见一片叶子。\n"
    assert "小猛说：下次再找朋友。" in (output / "book-text.md").read_text(encoding="utf-8")
    assert (output / "page-text-manifest.json").is_file()
    assert (output / "delivery-notes.md").is_file()
    assert (output / "delivery-validation.json").is_file()
    assert (output / "contact-sheet.png").is_file()
    assert not list(output.rglob("*.pptx"))
    with Image.open(output / "images" / "page-02.png") as image:
        assert image.size == (1080, 1440)

    manifest = json.loads((output / "page-text-manifest.json").read_text(encoding="utf-8"))
    assert manifest["pages"][0]["output_sha256"] == _sha256(output / "images" / "page-02.png")
    assert manifest["pages"][0]["build_action"] == "normalized"
    validation = json.loads((output / "delivery-validation.json").read_text(encoding="utf-8"))
    assert validation["status"] == "passed"
    assert validation["checks"]["visual_text_absence"] == "human_review_required"


def test_identical_build_is_a_safe_noop(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    output = tmp_path / "delivery-v1"
    build_delivery(root, "b01", output)
    validation = output / "delivery-validation.json"
    before_mtime = validation.stat().st_mtime_ns
    before_hash = _sha256(output / "images" / "page-02.png")

    result = build_delivery(root, "b01", output)

    assert result["status"] == "reused"
    assert result["cache_hits"] == 2
    assert validation.stat().st_mtime_ns == before_mtime
    assert _sha256(output / "images" / "page-02.png") == before_hash


def test_incomplete_existing_delivery_fails_closed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    output = tmp_path / "delivery-v1"
    build_delivery(root, "b01", output)
    (output / "contact-sheet.png").unlink()

    with pytest.raises(DeliveryError, match="OUTPUT_EXISTS_CORRUPT"):
        build_delivery(root, "b01", output)


def test_changed_input_never_overwrites_existing_delivery(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    output = tmp_path / "delivery-v1"
    build_delivery(root, "b01", output)
    original = (output / "text" / "page-02.txt").read_text(encoding="utf-8")
    storyboard_path = root / "books" / "b01" / "v0.1" / "storyboard.json"
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard["pages"][1]["text"] = "小熊看见两片叶子。"
    storyboard_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(DeliveryError, match="OUTPUT_EXISTS_DIFFERENT_INPUT"):
        build_delivery(root, "b01", output)

    assert (output / "text" / "page-02.txt").read_text(encoding="utf-8") == original


def test_reuse_from_rebuilds_only_changed_page(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    first = tmp_path / "delivery-v1"
    second = tmp_path / "delivery-v2"
    build_delivery(root, "b01", first)
    source = root / "books" / "b01" / "v0.1" / "images" / "pages" / "page-03-v0.1.png"
    _make_page(source, (1080, 1440), (220, 180, 240))

    result = build_delivery(root, "b01", second, reuse_from=first)

    assert result["status"] == "built"
    assert result["cache_hits"] == 1
    manifest = json.loads((second / "page-text-manifest.json").read_text(encoding="utf-8"))
    actions = {page["page"]: page["build_action"] for page in manifest["pages"]}
    assert actions == {2: "reused", 3: "normalized"}
    first_manifest = json.loads((first / "page-text-manifest.json").read_text(encoding="utf-8"))
    second_by_page = {page["page"]: page for page in manifest["pages"]}
    first_by_page = {page["page"]: page for page in first_manifest["pages"]}
    assert second_by_page[2]["output_sha256"] == first_by_page[2]["output_sha256"]
    assert second_by_page[3]["output_sha256"] != first_by_page[3]["output_sha256"]


def test_missing_page_fails_before_creating_output(tmp_path: Path) -> None:
    root = _fixture(tmp_path, include_page_03=False)
    output = tmp_path / "delivery-v1"

    with pytest.raises(DeliveryError, match="MISSING_PAGE_IMAGE"):
        build_delivery(root, "b01", output)

    assert not output.exists()


def test_wrong_aspect_ratio_fails_before_creating_output(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    bad = root / "books" / "b01" / "v0.1" / "images" / "pages" / "page-03-v0.1.png"
    _make_page(bad, (1000, 1000), (20, 20, 20))
    output = tmp_path / "delivery-v1"

    with pytest.raises(DeliveryError, match="ASPECT_RATIO_MISMATCH"):
        build_delivery(root, "b01", output)

    assert not output.exists()


def test_transparent_page_fails_before_creating_output(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    bad = root / "books" / "b01" / "v0.1" / "images" / "pages" / "page-03-v0.1.png"
    Image.new("RGBA", (1080, 1440), (20, 20, 20, 255)).save(bad)
    with Image.open(bad) as image:
        image.putpixel((0, 0), (0, 0, 0, 0))
        image.save(bad)
    output = tmp_path / "delivery-v1"

    with pytest.raises(DeliveryError, match="INVALID_ALPHA"):
        build_delivery(root, "b01", output)

    assert not output.exists()

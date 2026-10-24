import hashlib
import importlib.util
import json
import shutil
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


PROJECTS_DIR = Path(r"D:\宝宝绘本制作\projects")
LEGACY_PROJECT = PROJECTS_DIR / "phase4-autumn-leaves-3-4-2026-10-20"
SECOND_PROJECT = PROJECTS_DIR / "phase5-seed-growth-3-4-2026-10-20"
CONTENT_PROJECT = PROJECTS_DIR / "phase6-shadow-3-4-2026-10-20"
CONTENT_BOOK = CONTENT_PROJECT / "books" / "b01" / "v1" / "content"
CANDIDATE_05 = CONTENT_PROJECT / "books" / "b01" / "v1" / "review" / "recovery-candidates" / "PAGE-05-v2" / "page-05-v2-1080x1440.png"
CANDIDATE_08 = CONTENT_PROJECT / "books" / "b01" / "v1" / "review" / "recovery-candidates" / "PAGE-08-v2" / "page-08-v2-1080x1440.png"
BUSINESS_BOOK_ID = "phase6-shadow-3-4-2026-10-20-b01"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_project_json(source_project: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_project / "project.json", destination / "project.json")


def _copy_content_layout(tmp_path: Path, *, complete_pages: bool = True) -> Path:
    root = tmp_path / "content-project"
    _copy_project_json(CONTENT_PROJECT, root)
    destination_content = root / "books" / "b01" / "v1" / "content"
    shutil.copytree(CONTENT_BOOK, destination_content)
    if complete_pages:
        shutil.copy2(CANDIDATE_05, destination_content / "images" / "page-05.png")
        shutil.copy2(CANDIDATE_08, destination_content / "images" / "page-08.png")
        manifest_path = destination_content / "page-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            number = int(page["page"])
            if number in {5, 8}:
                page["current_image_path"] = f"images/page-{number:02d}.png"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return root


def _copy_legacy_layout(tmp_path: Path) -> Path:
    root = tmp_path / "legacy-project"
    _copy_project_json(LEGACY_PROJECT, root)
    shutil.copytree(LEGACY_PROJECT / "books" / "b01" / "v1", root / "books" / "b01" / "v1")
    return root


def _copy_second_project_layout(tmp_path: Path) -> Path:
    root = tmp_path / "second-project"
    _copy_project_json(SECOND_PROJECT, root)
    shutil.copytree(SECOND_PROJECT / "books" / "b01" / "v1", root / "books" / "b01" / "v1")
    return root


def test_legacy_version_root_layout_is_still_buildable(tmp_path: Path) -> None:
    root = _copy_legacy_layout(tmp_path)
    result = build_delivery(root, "b01", tmp_path / "legacy-delivery", version="v1")

    assert result["status"] == "built"
    assert result["model_generation_calls"] == 0
    assert result["page_count"] == 8


def test_second_project_legacy_root_storyboard_and_content_inputs_are_unambiguous(tmp_path: Path) -> None:
    root = _copy_second_project_layout(tmp_path)
    result = build_delivery(root, "b01", tmp_path / "second-delivery", version="v1")

    assert result["status"] == "built"
    validation = json.loads((tmp_path / "second-delivery" / "delivery-validation.json").read_text(encoding="utf-8"))
    assert validation["contract"]["layout"] == "content"
    assert validation["contract"]["business_book_id"] == "phase5-seed-growth-3-4-2026-10-20-b01"
    assert validation["checks"]["contract_inputs_loaded"] is True


def test_content_layout_reads_all_delivery_contract_inputs_and_business_id(tmp_path: Path) -> None:
    root = _copy_content_layout(tmp_path)
    output = tmp_path / "content-delivery"
    result = build_delivery(root, BUSINESS_BOOK_ID, output, version="v1")

    assert result["status"] == "built"
    assert result["page_count"] == 8
    manifest = json.loads((output / "page-text-manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "delivery-validation.json").read_text(encoding="utf-8"))
    assert manifest["book_id"] == BUSINESS_BOOK_ID
    assert manifest["age_band"] == "3-4"
    assert validation["contract"]["layout"] == "content"
    assert set(validation["contract"]["inputs"]) >= {
        "storyboard.json",
        "page-manifest.json",
        "page-text.json",
        "layout.json",
        "education-goal.json",
        "asset-binding-plan.json",
    }
    assert validation["checks"]["model_generation_calls"] == 0
    assert not list(output.rglob("*.pptx"))


def test_declared_image_path_prefers_canonical_book_image_over_content_preview(tmp_path: Path) -> None:
    root = _copy_content_layout(tmp_path)
    version = root / "books" / "b01" / "v1"
    formal_dir = version / "images"
    formal_dir.mkdir(parents=True)
    shutil.copy2(version / "content" / "images" / "page-01.png", formal_dir / "page-01.png")

    from project_paths import resolve_book_image_file

    manifest = json.loads((version / "content" / "page-manifest.json").read_text(encoding="utf-8"))
    local_spec = importlib.util.spec_from_file_location(
        "build_pure_image_delivery_canonical_path_test",
        SCRIPTS_DIR / "build_pure_image_delivery.py",
    )
    local_module = importlib.util.module_from_spec(local_spec)
    sys.modules[local_spec.name] = local_module
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        local_spec.loader.exec_module(local_module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        sys.modules.pop(local_spec.name, None)
    candidate = local_module._candidate_images(
        version,
        root,
        manifest["pages"][0],
        content_dir=version / "content",
    )[0]

    assert candidate == (formal_dir / "page-01.png").resolve()


def test_full_eight_page_isolated_build_has_ordered_images_and_preserves_sources(tmp_path: Path) -> None:
    root = _copy_content_layout(tmp_path)
    source_hashes_before = {
        page: _sha256(root / "books" / "b01" / "v1" / "content" / "images" / f"page-{page:02d}.png")
        for page in (1, 2, 3, 4, 5, 6, 7, 8)
    }
    output = tmp_path / "isolated-delivery"

    result = build_delivery(root, "b01", output, version="v1")

    assert result["status"] == "built"
    assert result["page_count"] == 8
    manifest = json.loads((output / "page-text-manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "delivery-validation.json").read_text(encoding="utf-8"))
    assert [page["page"] for page in manifest["pages"]] == list(range(1, 9))
    assert validation["status"] == "passed"
    assert validation["page_count"] == 8
    assert validation["checks"]["all_images_exact_1080x1440"] is True
    for page in range(1, 9):
        image_path = output / "images" / f"page-{page:02d}.png"
        with Image.open(image_path) as image:
            assert image.size == (1080, 1440)
            assert image.mode == "RGB"
        assert image_path.is_file()
    assert source_hashes_before == {
        page: _sha256(root / "books" / "b01" / "v1" / "content" / "images" / f"page-{page:02d}.png")
        for page in source_hashes_before
    }


@pytest.mark.parametrize(
    "case",
    [
        "missing-book",
        "missing-version",
        "missing-storyboard",
        "conflicting-layouts",
        "missing-image",
        "path-escape",
    ],
)
def test_abnormal_project_structures_fail_closed(tmp_path: Path, case: str) -> None:
    root = _copy_content_layout(tmp_path)
    book = root / "books" / "b01"
    version = book / "v1"
    content = version / "content"
    if case == "missing-book":
        with pytest.raises(DeliveryError, match="BOOK_ID_NOT_FOUND"):
            build_delivery(root, "not-a-book", tmp_path / "out", version="v1")
        return
    if case == "missing-version":
        with pytest.raises(DeliveryError, match="BOOK_VERSION_NOT_FOUND"):
            build_delivery(root, "b01", tmp_path / "out", version="missing")
        return
    if case == "missing-storyboard":
        (content / "storyboard.json").unlink()
        with pytest.raises(DeliveryError, match="STORYBOARD_MISSING"):
            build_delivery(root, "b01", tmp_path / "out", version="v1")
        return
    if case == "conflicting-layouts":
        version.mkdir(parents=True, exist_ok=True)
        (version / "storyboard.json").write_text("{\"pages\": []}\n", encoding="utf-8")
        with pytest.raises(DeliveryError, match="CONTENT_LAYOUT_CONFLICT"):
            build_delivery(root, "b01", tmp_path / "out", version="v1")
        return
    if case == "missing-image":
        (content / "images" / "page-04.png").unlink()
        with pytest.raises(DeliveryError, match="MISSING_PAGE_IMAGE:4"):
            build_delivery(root, "b01", tmp_path / "out", version="v1")
        return
    manifest_path = content / "page-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][0]["current_image_path"] = "../../../../outside.png"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(DeliveryError, match="IMAGE_PATH_ESCAPES_BOOK"):
        build_delivery(root, "b01", tmp_path / "out", version="v1")


def test_business_id_cannot_silently_select_a_different_version(tmp_path: Path) -> None:
    root = _copy_content_layout(tmp_path)
    second_version = root / "books" / "b01" / "v2" / "content"
    shutil.copytree(root / "books" / "b01" / "v1" / "content", second_version)
    storyboard_path = second_version / "storyboard.json"
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard["book_id"] = "another-business-book"
    storyboard_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in ("page-manifest.json", "page-text.json", "layout.json", "asset-binding-plan.json"):
        metadata_path = second_version / name
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["book_id"] = "another-business-book"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(DeliveryError, match="BOOK_ID_VERSION_CONFLICT"):
        build_delivery(root, BUSINESS_BOOK_ID, tmp_path / "out", version="v2")


def test_repeated_build_reuses_complete_delivery_without_model_calls(tmp_path: Path) -> None:
    root = _copy_content_layout(tmp_path)
    output = tmp_path / "repeat-delivery"
    first = build_delivery(root, "b01", output, version="v1")
    validation_path = output / "delivery-validation.json"
    validation_hash_before = _sha256(validation_path)

    second = build_delivery(root, "b01", output, version="v1")

    assert first["status"] == "built"
    assert second["status"] == "reused"
    assert second["cache_hits"] == 8
    assert second["model_generation_calls"] == 0
    assert _sha256(validation_path) == validation_hash_before

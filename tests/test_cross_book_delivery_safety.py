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
    from build_pure_image_delivery import build_delivery
    from incremental_archive import ArchiveError, build_incremental_archive
finally:
    sys.path.remove(str(SCRIPTS_DIR))

sys.path.insert(0, str(Path(__file__).parent))
try:
    from test_phase3_preflight_archive import _fixture, _write_json
finally:
    sys.path.remove(str(Path(__file__).parent))


def _clone_b02(root: Path) -> None:
    source = root / "books" / "b01"
    target = root / "books" / "b02"
    shutil.copytree(source, target)
    project_path = root / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["books"].append({**project["books"][0], "id": "b02"})
    _write_json(project_path, project)
    for path in (target / "v1" / "content").rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("book_id") == "test-book-b01":
            data["book_id"] = "test-book-b02"
            _write_json(path, data)


def _build_root_delivery(root: Path, book_id: str) -> Path:
    output = root / "pure-image-delivery" / book_id
    build_delivery(root, book_id, output, version="v1")
    return output


def _two_book_project(tmp_path: Path, *, b01_delivery: bool, b02_delivery: bool) -> Path:
    root = _fixture(tmp_path, with_images=True)
    shutil.rmtree(root / "books" / "b01" / "v1" / "delivery")
    _clone_b02(root)
    if b01_delivery:
        _build_root_delivery(root, "b01")
    if b02_delivery:
        _build_root_delivery(root, "b02")
    return root


def test_target_without_delivery_does_not_reuse_other_book(tmp_path: Path) -> None:
    root = _two_book_project(tmp_path, b01_delivery=False, b02_delivery=True)
    with pytest.raises(ArchiveError, match="ARCHIVE_DELIVERY_IDENTITY_MISMATCH"):
        build_incremental_archive(root, "b01", tmp_path / "audit" / "b01", version="v1")


def test_two_valid_deliveries_select_the_requested_book(tmp_path: Path) -> None:
    root = _two_book_project(tmp_path, b01_delivery=True, b02_delivery=True)
    result = build_incremental_archive(root, "b01", tmp_path / "audit" / "b01", version="v1")
    manifest = json.loads((Path(result["archive"]) / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    assert result["status"] == "built"
    delivery_sources = [
        str(entry["source_path"]).replace("\\", "/")
        for entry in manifest["entries"]
        if entry.get("use") == "independent_pure_image_delivery"
    ]
    assert delivery_sources
    assert all("pure-image-delivery/b01/" in source for source in delivery_sources)
    assert all("pure-image-delivery/b02/" not in source for source in delivery_sources)


def test_delivery_book_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _two_book_project(tmp_path, b01_delivery=True, b02_delivery=True)
    validation_path = root / "pure-image-delivery" / "b01" / "delivery-validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["book_id"] = "test-book-b02"
    _write_json(validation_path, validation)
    with pytest.raises(ArchiveError, match="ARCHIVE_DELIVERY_IDENTITY_MISMATCH"):
        build_incremental_archive(root, "b01", tmp_path / "audit" / "b01", version="v1")


def test_delivery_source_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _two_book_project(tmp_path, b01_delivery=True, b02_delivery=True)
    image_path = root / "books" / "b01" / "v1" / "content" / "images" / "page-01.png"
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.putpixel((0, 0), (0, 0, 0))
        image.save(image_path, format="PNG", optimize=False)
    with pytest.raises(ArchiveError, match="ARCHIVE_DELIVERY_IDENTITY_MISMATCH"):
        build_incremental_archive(root, "b01", tmp_path / "audit" / "b01", version="v1")


def test_same_input_reuses_but_changed_archive_input_does_not_reuse(tmp_path: Path) -> None:
    root = _two_book_project(tmp_path, b01_delivery=True, b02_delivery=True)
    target = tmp_path / "audit" / "b01"
    first = build_incremental_archive(root, "b01", target, version="v1")
    second = build_incremental_archive(root, "b01", target, version="v1")
    assert first["status"] == "built"
    assert second["status"] == "reused"
    (root / "research" / "research_packet.md").write_text("# changed\n", encoding="utf-8")
    changed = build_incremental_archive(root, "b01", target, version="v1")
    assert changed["status"] == "built"
    assert Path(changed["archive"]) != target
    assert (target / "ARCHIVE_MANIFEST.json").is_file()


@pytest.mark.parametrize(
    "source_name",
    [
        "phase4-autumn-leaves-3-4-2026-10-20",
        "phase5-seed-growth-3-4-2026-10-20",
        "phase6-shadow-3-4-2026-10-20",
    ],
)
def test_real_project_copies_remain_archive_compatible(tmp_path: Path, source_name: str) -> None:
    source = Path("D:/宝宝绘本制作/projects") / source_name
    if not source.is_dir():
        pytest.skip(f"real project unavailable: {source}")
    root = tmp_path / source_name
    shutil.copytree(source, root)
    result = build_incremental_archive(root, "b01", tmp_path / "audit" / source_name, version="v1")
    assert result["status"] == "built"
    manifest = json.loads((Path(result["archive"]) / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["model_generation_calls"] == 0


def test_interrupted_cross_book_archive_leaves_no_complete_marker(tmp_path: Path) -> None:
    root = _two_book_project(tmp_path, b01_delivery=True, b02_delivery=True)
    target = tmp_path / "audit" / "b01"
    with pytest.raises(ArchiveError, match="ARCHIVE_SIMULATED_INTERRUPTION"):
        build_incremental_archive(root, "b01", target, version="v1", fail_after_copies=1)
    assert not target.exists()
    assert not list(target.parent.glob(".*.tmp"))

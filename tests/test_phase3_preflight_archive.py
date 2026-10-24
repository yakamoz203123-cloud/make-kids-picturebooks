import json
import shutil
from pathlib import Path

import pytest
from PIL import Image


SKILL_DIR = Path(__file__).parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from incremental_archive import ArchiveError, build_incremental_archive
    from build_pure_image_delivery import build_delivery
    from project_preflight import preflight_project
finally:
    sys.path.remove(str(SCRIPTS_DIR))


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path, *, with_images: bool = False) -> Path:
    root = tmp_path / "project"
    book = root / "books" / "b01" / "v1"
    content = book / "content"
    _write_json(
        root / "project.json",
        {
            "schema_version": 1,
            "title": "测试小书",
            "target_age_bands": ["3-4"],
            "characters_version": "core-characters-v1.3",
            "style_id": "STYLE-06",
            "style_version": "v0.1",
            "source": {"path": "research/research_packet.md", "version": "packet-v1", "coverage": "test"},
            "books": [{"id": "b01", "age_band": "3-4", "status": "text", "source_version": "packet-v1", "characters_version": "core-characters-v1.3"}],
        },
    )
    research = root / "research"
    for name in ("research_packet.md", "sources.json", "claims.json", "child_concepts.json"):
        (research / name).parent.mkdir(parents=True, exist_ok=True)
        (research / name).write_text("{}\n" if name.endswith(".json") else "# research\n", encoding="utf-8")
    (content / "prompts").mkdir(parents=True, exist_ok=True)
    (content / "characters" / "core-v1.3" / "reference").mkdir(parents=True, exist_ok=True)
    (content / "styles" / "style-06-v0.1").mkdir(parents=True, exist_ok=True)
    (content / "prompts" / "page-01.md").write_text("prompt\n", encoding="utf-8")
    Image.new("RGB", (12, 12), (220, 180, 120)).save(content / "characters" / "core-v1.3" / "reference" / "ref.png")
    _write_json(
        content / "characters" / "core-v1.3" / "approval.json",
        {"release_status": "released", "production_enabled": True, "formal_production_approval": {"status": "approved"}},
    )
    _write_json(
        content / "styles" / "style-06-v0.1" / "approval.json",
        {"visual_approval_status": "approved", "formal_production_approval_status": "approved", "production_enabled_for_explicit_selection": True},
    )
    story = "小熊看见一颗种子。\n"
    (content / "story.md").write_text(story, encoding="utf-8")
    pages = [
        {
            "page": 1,
            "page_id": "PAGE-01",
            "page_version": "PAGE-01-v1",
            "story_version": "story-v1",
            "text_version": "v1",
            "text": "小熊看见一颗种子。",
            "characters_version": "v1.3",
            "character_asset_bundle": "core-characters-v1.3",
            "character_asset_version": "v1.3",
            "style_master_id": "STYLE-06",
            "style_master_version": "v0.1",
            "declared_aspect_ratio": "3:4",
            "current_prompt_path": "prompts/page-01.md",
            "current_image_path": "images/page-01.png" if with_images else None,
            "character_reference_path": "characters/core-v1.3/reference/ref.png",
            "production_reference_path": "characters/core-v1.3/reference/ref.png",
            "text_area": [1, 1, 10, 10],
            "props": [],
            "knowledge_check": {"status": "passed" if with_images else "pending", "evidence": "observed"},
            "layout_design": {
                "layout_style_version": "layout-v1",
                "layout_mode": "scene-integrated",
                "text_anchor": "top-left",
                "text_treatment": "natural-space",
                "text_align": "left",
                "max_lines": 3,
                "focal_point": "seed",
                "text_safe_area": "top",
                "avoid_covering": [],
                "avoid_covering_reason": "keep focal point clear",
                "page_rhythm": "establishing",
                "palette_token": "warm-paper",
                "status": "passed",
                "social_layout": {
                    "profile": "xiaohongshu-feed-3x4",
                    "canvas": {"width_px": 1080, "height_px": 1440},
                    "subject_safe_area": [0.1, 0.2, 0.8, 0.6],
                    "text_safe_area": [0.1, 0.05, 0.7, 0.1],
                    "avoid_regions": [],
                    "source_aspect_ratio": "3:4",
                    "composition_mode": "portrait-full-bleed",
                    "text_placement": "in-scene",
                    "status": "passed",
                },
            },
            "previous_page_state": {"state_id": "story_start", "summary": "start"},
            "current_page_entry": {"state_id": "story_start", "summary": "start"},
            "next_page_hook": {"state_id": "story_end", "summary": "end"},
            "text_image_match": {"status": "passed" if with_images else "pending", "evidence": "matched"},
            "continuity_review": {"status": "passed" if with_images else "pending", "evidence": "matched"},
        }
    ]
    storyboard = {"schema_version": 1, "book_id": "test-book-b01", "version": "v1", "title": "测试小书", "age_band": "3-4", "pages": pages}
    _write_json(content / "storyboard.json", storyboard)
    manifest = {"schema_version": 1, "book_id": "test-book-b01", "age_band": "3-4", "research_packet_path": "../../../research", "knowledge_whitelist_path": "../review/knowledge-whitelist.json", "story_claim_trace_path": "../review/story-claim-trace.json", "pages": pages}
    _write_json(content / "page-manifest.json", manifest)
    _write_json(content / "page-text.json", {"pages": [{"page": 1, "text": pages[0]["text"]}]})
    _write_json(content / "layout.json", {"pages": [{"page": 1, "style_version": "v0.1"}]})
    _write_json(content / "education-goal.json", {"book_id": "test-book-b01", "goal": "observe"})
    _write_json(content / "asset-binding-plan.json", {"user_selected_assets": {"character_formal_production_approval": "approved", "style_formal_production_approval": "approved", "style_status": "approved"}})
    _write_json(book / "review" / "knowledge-whitelist.json", {"claims": {}})
    _write_json(book / "review" / "story-claim-trace.json", {"pages": []})
    if with_images:
        image_dir = content / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1080, 1440), (240, 220, 180)).save(image_dir / "page-01.png", format="PNG", optimize=False)
        _write_json(book / "review" / "review.json", {"user_final_approval": True, "pages": [{"page": 1, "status": "approved"}]})
        delivery = book / "delivery" / "pure-image-delivery-v1"
        build_delivery(root, "b01", delivery, version="v1")
    return root


def test_pre_generation_allows_missing_images_and_does_not_write_queue(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict")
    assert result["status"] == "passed"
    assert result["write_operations"] == 0
    assert not list(root.rglob("production-queue.json"))


def test_pre_generation_reports_complete_production_dependency_closure(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict")
    closure = result["production_dependency_closure"]
    assert closure["status"] == "passed"
    assert closure["profile"] == "production-ready"
    assert closure["missing"] == []
    assert closure["outside_book"] == []


def test_pre_generation_blocks_missing_production_dependencies_with_field_context(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    book = root / "books" / "b01" / "v1" / "content"
    (book / "prompts" / "page-01.md").unlink()
    (book / "characters" / "core-v1.3" / "reference" / "ref.png").unlink()

    result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict")
    closure = result["production_dependency_closure"]
    assert closure["status"] == "blocked"
    assert any("PRODUCTION_DEPENDENCY_MISSING:page=1:field=current_prompt_path" in item for item in result["blockers"])
    assert any("PRODUCTION_DEPENDENCY_MISSING:page=1:field=character_reference_path" in item for item in result["blockers"])


def test_delivery_only_profile_is_not_production_ready(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    project_path = root / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["project_profile"] = "delivery-only"
    _write_json(project_path, project)

    result = preflight_project(root, "b01", version="v1", phase="pre_generation", mode="strict")
    assert result["production_dependency_closure"]["profile"] == "delivery-only"
    assert "PROJECT_PROFILE_NOT_PRODUCTION_READY" in result["blockers"]


def test_pre_delivery_blocks_missing_formal_image(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    result = preflight_project(root, "b01", version="v1", phase="pre_delivery")
    assert result["status"] == "blocked"
    assert any("FORMAL_IMAGE" in item for item in result["blockers"])


def test_missing_storyboard_and_age_conflict_are_reported(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    (root / "books" / "b01" / "v1" / "content" / "storyboard.json").unlink()
    missing = preflight_project(root, "b01", version="v1", phase="pre_generation")
    assert missing["status"] == "blocked"
    assert any("CONTRACT_INVALID" in item for item in missing["blockers"])

    root = _fixture(tmp_path / "age", with_images=False)
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    project["target_age_bands"] = ["5-7"]
    _write_json(root / "project.json", project)
    conflict = preflight_project(root, "b01", version="v1", phase="pre_generation")
    assert "AGE_BAND_CONFLICT" in conflict["blockers"]


def test_path_escape_and_continuity_block_are_not_ignored(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    manifest_path = root / "books" / "b01" / "v1" / "content" / "page-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][0]["current_prompt_path"] = "../../outside.md"
    manifest["pages"][0]["continuity_invariants"] = {"science_stages": "invalid"}
    _write_json(manifest_path, manifest)
    result = preflight_project(root, "b01", version="v1", phase="pre_generation")
    assert result["status"] == "blocked"
    assert any("PAGE_PATH_ESCAPES_BOOK" in item for item in result["blockers"])
    assert any("CONTINUITY_BLOCK" in item for item in result["blockers"])


def test_invalid_approval_and_conflicting_authority_are_blocked(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=False)
    approval = root / "books" / "b01" / "v1" / "content" / "styles" / "style-06-v0.1" / "approval.json"
    data = json.loads(approval.read_text(encoding="utf-8"))
    data["formal_production_approval_status"] = "rejected"
    _write_json(approval, data)
    result = preflight_project(root, "b01", version="v1", phase="pre_generation")
    assert "STYLE_APPROVAL_INVALID" in result["blockers"]

    root = _fixture(tmp_path / "authority", with_images=False)
    _write_json(root / "books" / "b01" / "v1" / "storyboard.json", {"pages": []})
    conflict = preflight_project(root, "b01", version="v1", phase="pre_generation")
    assert any("PROJECT_RESOLUTION:CONTENT_LAYOUT_CONFLICT" in item for item in conflict["blockers"])


def test_pre_delivery_accepts_complete_fixture(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    result = preflight_project(root, "b01", version="v1", phase="pre_delivery", mode="strict")
    assert result["status"] == "passed"
    assert result["image_model_calls"] == 0


def test_incremental_archive_reuses_and_versions_without_nesting(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    target = tmp_path / "audit" / "trial-v1"
    first = build_incremental_archive(root, "b01", target, version="v1")
    second = build_incremental_archive(root, "b01", target, version="v1")
    assert first["status"] == "built"
    assert first["copied_file_count"] > 0
    assert first["copied_bytes"] > 0
    assert second["status"] == "reused"
    assert (target / "ARCHIVE_MANIFEST.json").is_file()
    assert not (target / "archive").exists()

    research = root / "research" / "research_packet.md"
    research.write_text("# changed research\n", encoding="utf-8")
    changed = build_incremental_archive(root, "b01", target, version="v1")
    assert changed["status"] == "built"
    assert Path(changed["archive"]) != target
    assert target.is_dir()


def test_archive_requires_a_real_independent_delivery(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    shutil.rmtree(root / "books" / "b01" / "v1" / "delivery")
    with pytest.raises(ArchiveError, match="ARCHIVE_DELIVERY_MISSING"):
        build_incremental_archive(root, "b01", tmp_path / "audit" / "trial-v1", version="v1")


def test_archive_interruption_cleans_stage_and_does_not_mark_complete(tmp_path: Path) -> None:
    root = _fixture(tmp_path, with_images=True)
    target = tmp_path / "audit" / "trial-v1"
    with pytest.raises(ArchiveError, match="ARCHIVE_SIMULATED_INTERRUPTION"):
        build_incremental_archive(root, "b01", target, version="v1", fail_after_copies=1)
    assert not target.exists()
    assert not list(target.parent.glob(".*.tmp")) if target.parent.exists() else True

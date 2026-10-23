import copy
import json
import sys
from pathlib import Path

import pytest
from PIL import Image


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
ASSET_BUNDLE = SKILL / "assets" / "characters" / "core-v1.3"
STYLE_BUNDLE = SKILL / "assets" / "style-06-v0.1"
sys.path.insert(0, str(SCRIPTS))

from asset_resolver import resolve_page_assets  # noqa: E402
from page_production import complete_page  # noqa: E402


def _page() -> dict:
    page = json.loads((SKILL / "assets" / "page-production-template.json").read_text(encoding="utf-8"))
    page.update(
        {
            "character_asset_bundle": "core-characters-v1.3",
            "character_asset_version": "v1.3",
            "style_master_id": "STYLE-06",
            "style_master_version": "v0.1",
            "style_master_content_hash": "45cb24e2ecfec2f00567528eb6dc0c894edeafaa08582a1e9f250e265bf82c8e",
            "characters": [
                {
                    "character_id": "CHAR-GIRL-01",
                    "outfit_id": "G-01",
                    "expression_id": "G-EX-02",
                    "pose_id": "G-PO-01",
                    "angle_id": "ANG-01",
                }
            ],
            "page_delta": {"scene": "autumn path", "knowledge_evidence": "visible leaves"},
            "text": "小熊看见一片叶子。",
            "text_safe_area": [72, 72, 480, 180],
            "continuity": {"entry": "start", "exit": "next"},
            "source_prompt_hash": "a" * 64,
            "resolved_asset_hash": "[pending]",
            "review_status": "planning",
            "shot_id": "SHOT-OBSERVE-01",
            "declared_aspect_ratio": "3:4",
        }
    )
    return page


def test_explicit_approved_style06_resolves_with_core_v13():
    manifest = json.loads((ASSET_BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    aliases = json.loads((ASSET_BUNDLE / "aliases.json").read_text(encoding="utf-8"))["aliases"]

    result = resolve_page_assets(
        manifest,
        _page(),
        aliases,
        bundle_root=ASSET_BUNDLE,
        style_bundle_root=STYLE_BUNDLE,
        mode="production",
    )

    assert result["ok"], result
    assert result["asset_selection"]["style_master_id"] == "STYLE-06"
    assert result["asset_selection"]["style_master_version"] == "v0.1"


def test_single_character_action_reference_can_support_a_two_character_page():
    manifest = json.loads((ASSET_BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    aliases = json.loads((ASSET_BUNDLE / "aliases.json").read_text(encoding="utf-8"))["aliases"]
    page = _page()
    page["characters"].append(
        {
            "character_id": "CHAR-BOY-01",
            "outfit_id": "B-01",
            "expression_id": "B-EX-02",
            "pose_id": "B-PO-03",
            "angle_id": "ANG-02",
        }
    )
    page["interaction_id"] = "DUO-04"
    page["character_reference_assets"] = [{"asset_id": "G-ACT-A-01"}]

    result = resolve_page_assets(
        manifest,
        page,
        aliases,
        bundle_root=ASSET_BUNDLE,
        style_bundle_root=STYLE_BUNDLE,
        mode="production",
    )

    assert result["ok"], result


def test_formal_page_rejects_non_opaque_wrong_size_rgba(tmp_path: Path):
    image_path = tmp_path / "bad-sample.png"
    image = Image.new("RGBA", (1086, 1448), (255, 255, 255, 0))
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(image_path)

    with pytest.raises(ValueError, match="INVALID_DIMENSIONS"):
        complete_page(_page(), image_path)


def test_formal_page_rejects_non_opaque_exact_size_rgba(tmp_path: Path):
    image_path = tmp_path / "transparent-sample.png"
    Image.new("RGBA", (1080, 1440), (255, 255, 255, 255)).save(image_path)
    with Image.open(image_path) as image:
        image.putpixel((0, 0), (0, 0, 0, 0))
        image.save(image_path)

    with pytest.raises(ValueError, match="INVALID_ALPHA"):
        complete_page(_page(), image_path)


def test_formal_page_accepts_exact_opaque_rgb(tmp_path: Path):
    image_path = tmp_path / "good-sample.png"
    Image.new("RGB", (1080, 1440), "white").save(image_path)

    result = complete_page(_page(), image_path)

    assert result["status"] == "completed"
    assert result["dimensions"] == [1080, 1440]

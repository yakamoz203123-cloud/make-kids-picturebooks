from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asset_resolver import load_core_manifest, resolve_page_assets
from generation_queue import init_queue
from page_production import build_page_prompt
from page_versions import affected_pages, image_dependency_fingerprint
from prepare_character_references import prepare_page_references


PHASE2E = Path(r"D:\宝宝绘本制作\projects\character-assets-phase2e-2026-10-19")
BUNDLE = PHASE2E / "staged-assets" / "core-v1.3"
V13_MANIFEST = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
TEMPLATE = json.loads((ROOT / "assets" / "page-production-template.json").read_text(encoding="utf-8"))


def page_for(character: str, outfit: str, expression: str, pose: str, auxiliary: list[str] | None = None) -> dict:
    page = copy.deepcopy(TEMPLATE)
    page["character_asset_bundle"] = "core-characters-v1.3"
    page["character_asset_version"] = "v1.3"
    page["characters_version"] = "v1.3"
    page["characters"] = [{
        "character_id": character,
        "outfit_id": outfit,
        "expression_id": expression,
        "pose_id": pose,
        "angle_id": "ANG-01",
    }]
    if auxiliary is not None:
        page["character_reference_assets"] = [{"asset_id": item} for item in auxiliary]
    return page


class Phase2EAssetVersioningTests(unittest.TestCase):
    def test_v12_is_still_the_default_and_v13_is_not_production_enabled(self):
        default = load_core_manifest()
        self.assertEqual(default["bundle_id"], "core-characters-v1.2")
        self.assertEqual(build_page_prompt(TEMPLATE)["asset_selection"]["version"], "v1.2")
        self.assertEqual(V13_MANIFEST["bundle_id"], "core-characters-v1.3")
        self.assertEqual(V13_MANIFEST["release_status"], "pending_approval")
        self.assertFalse(V13_MANIFEST["production_enabled"])

    def test_v13_resolves_each_identity_and_rejects_wrong_auxiliary_binding(self):
        pages = [
            page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01"),
            page_for("CHAR-BOY-01", "B-01", "B-EX-02", "B-PO-01"),
            page_for("CHAR-MOTHER-01", "M-01", "M-EX-01", "M-PO-01"),
        ]
        expected = {
            "xiaoxiong": "reference/xiaoxiong-fullbody-v2.png",
            "xiaomeng": "reference/xiaomeng-fullbody-v2.png",
            "mother": "reference/mother-fullbody-v1.png",
        }
        for page in pages:
            result = resolve_page_assets(V13_MANIFEST, page, bundle_root=BUNDLE, mode="planning")
            self.assertTrue(result["ok"], result)
            identities = [
                item for item in result["asset_selection"]["reference_selection"]
                if item["reference_purpose"] == "identity"
            ]
            self.assertEqual(len(identities), 1)
            self.assertEqual(identities[0]["reference_file"], expected[identities[0]["character_id"]])

        bad = page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01", ["G-ACT-B-01"])
        self.assertTrue(resolve_page_assets(V13_MANIFEST, bad, bundle_root=BUNDLE, mode="planning")["ok"])
        bad["character_reference_assets"] = [{"asset_id": "G-ACT-A-01"}]
        bad["characters"][0]["character_id"] = "CHAR-BOY-01"
        bad["characters"][0]["outfit_id"] = "B-01"
        bad["characters"][0]["expression_id"] = "B-EX-02"
        bad["characters"][0]["pose_id"] = "B-PO-01"
        self.assertEqual(
            resolve_page_assets(V13_MANIFEST, bad, bundle_root=BUNDLE, mode="planning")["failure"]["failure_code"],
            "INCOMPATIBLE_ASSET",
        )

        group = copy.deepcopy(TEMPLATE)
        group.update(
            character_asset_bundle="core-characters-v1.3",
            character_asset_version="v1.3",
            characters_version="v1.3",
            character_reference_assets=[{"asset_id": "GROUP-REF-01"}],
            characters=[
                {"character_id": "CHAR-GIRL-01", "outfit_id": "G-01", "expression_id": "G-EX-02", "pose_id": "G-PO-01", "angle_id": "ANG-01"},
                {"character_id": "CHAR-BOY-01", "outfit_id": "B-01", "expression_id": "B-EX-02", "pose_id": "B-PO-01", "angle_id": "ANG-01"},
                {"character_id": "CHAR-MOTHER-01", "outfit_id": "M-01", "expression_id": "M-EX-01", "pose_id": "M-PO-01", "angle_id": "ANG-01"},
            ],
        )
        group_result = resolve_page_assets(V13_MANIFEST, group, bundle_root=BUNDLE, mode="planning")
        self.assertTrue(group_result["ok"], group_result)
        self.assertIn("reference/three-character-group.png", {item["reference_file"] for item in group_result["asset_selection"]["reference_selection"]})

    def test_v13_is_explicitly_blocked_from_production(self):
        page = page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01")
        result = resolve_page_assets(V13_MANIFEST, page, bundle_root=BUNDLE, mode="production")
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure"]["failure_code"], "ASSET_STATUS_NOT_APPROVED")
        with self.assertRaisesRegex(ValueError, "ASSET_MANIFEST_REQUIRED_FOR_SELECTED_VERSION"):
            build_page_prompt(page)

    def test_reference_preparation_materializes_actual_v13_files_and_queue_receives_them(self):
        page = page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01", ["G-ACT-A-01"])
        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            updated, selection = prepare_page_references(
                page,
                manifest=V13_MANIFEST,
                bundle_root=BUNDLE,
                book_dir=book,
                mode="planning",
            )
            self.assertEqual(updated["character_asset_version"], "v1.3")
            self.assertTrue(updated["character_reference_path"].startswith("characters/core-characters-v1.3/"))
            self.assertEqual({item["asset_id"] for item in updated["character_reference_assets"]}, {"G-ACT-A-01"})
            self.assertIn("G-ID-01", {item["asset_id"] for item in selection["references"]})
            self.assertEqual(selection["asset_bundle"] if "asset_bundle" in selection else "core-characters-v1.3", "core-characters-v1.3")

            (book / "story.md").write_text("小熊观察一片叶子。\n", encoding="utf-8")
            (book / "prompts").mkdir()
            (book / "prompts" / "page-01.md").write_text("prompt\n", encoding="utf-8")
            (book / "storyboard.json").write_text(json.dumps({"pages": [{"page": 1}]}, ensure_ascii=False), encoding="utf-8")
            (book / "layout.json").write_text(json.dumps({"pages": [{"page": 1}]}, ensure_ascii=False), encoding="utf-8")
            updated["current_prompt_path"] = "prompts/page-01.md"
            updated["current_image_path"] = None
            (book / "page-manifest.json").write_text(json.dumps({"title": "test", "age_band": "3-4", "pages": [updated]}, ensure_ascii=False), encoding="utf-8")
            state = init_queue(book, book / "generation-queue.json")
            job = state["jobs"][0]
            self.assertEqual(job["character_reference_path"], updated["character_reference_path"])
            self.assertEqual({item["asset_id"] for item in job["reference_assets"]}, {"G-ACT-A-01"})
            self.assertTrue(all(item["path"].startswith("characters/core-characters-v1.3/") for item in job["reference_assets"]))
            self.assertTrue(all(len(item["sha256"]) == 64 for item in job["reference_assets"]))

    def test_identity_references_are_not_written_to_auxiliary_reference_field(self):
        page = page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01", ["G-ACT-A-01"])
        with tempfile.TemporaryDirectory() as temporary:
            updated, selection = prepare_page_references(
                page,
                manifest=V13_MANIFEST,
                bundle_root=BUNDLE,
                book_dir=Path(temporary),
                mode="planning",
            )

            self.assertEqual(
                {item["asset_id"] for item in updated["character_reference_assets"]},
                {"G-ACT-A-01"},
            )
            self.assertTrue(updated["character_reference_path"].endswith("-xiaoxiong-fullbody-v2.png"))
            selected_ids = {item["asset_id"] for item in selection["references"]}
            self.assertIn("G-ID-01", selected_ids)
            self.assertIn("G-ACT-A-01", selected_ids)

    def test_multiple_identity_references_use_primary_binding_and_keep_group_auxiliary_separate(self):
        page = copy.deepcopy(TEMPLATE)
        page.update(
            character_asset_bundle="core-characters-v1.3",
            character_asset_version="v1.3",
            characters_version="v1.3",
            character_reference_assets=[{"asset_id": "GROUP-REF-01"}],
            characters=[
                {"character_id": "CHAR-GIRL-01", "outfit_id": "G-01", "expression_id": "G-EX-02", "pose_id": "G-PO-01", "angle_id": "ANG-01"},
                {"character_id": "CHAR-MOTHER-01", "outfit_id": "M-01", "expression_id": "M-EX-01", "pose_id": "M-PO-01", "angle_id": "ANG-01"},
            ],
        )
        with tempfile.TemporaryDirectory() as temporary:
            updated, selection = prepare_page_references(
                page,
                manifest=V13_MANIFEST,
                bundle_root=BUNDLE,
                book_dir=Path(temporary),
                mode="planning",
            )

            self.assertEqual(
                {item["asset_id"] for item in updated["character_reference_assets"]},
                {"GROUP-REF-01"},
            )
            self.assertTrue(updated["character_reference_path"].endswith("-xiaoxiong-fullbody-v2.png"))
            selected_ids = {item["asset_id"] for item in selection["references"]}
            self.assertTrue({"G-ID-01", "M-ID-01", "GROUP-REF-01"}.issubset(selected_ids))

    def test_version_and_auxiliary_changes_are_page_local_cache_dependencies(self):
        v12 = copy.deepcopy(TEMPLATE)
        v13 = page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01", ["G-ACT-A-01"])
        self.assertNotEqual(image_dependency_fingerprint(v12), image_dependency_fingerprint(v13))
        first = copy.deepcopy(v12)
        first.update({"page_id": "PAGE-01", "page_version": "PAGE-01-v1"})
        second = copy.deepcopy(v12)
        second.update({"page_id": "PAGE-02", "page_version": "PAGE-02-v1"})
        before = [first, second]
        after = copy.deepcopy(before)
        after[1]["character_asset_version"] = "v1.3"
        after[1]["character_asset_bundle"] = "core-characters-v1.3"
        after[1]["character_reference_assets"] = [{"asset_id": "G-ACT-A-01", "path": "x", "sha256": "y"}]
        changed = affected_pages(before, after)
        self.assertEqual(changed["image_redraw"], ["PAGE-02"])
        self.assertEqual(changed["text_only"], [])

    def test_queue_fails_closed_on_wrong_materialized_reference_hash(self):
        page = page_for("CHAR-GIRL-01", "G-01", "G-EX-02", "G-PO-01", ["G-ACT-A-01"])
        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            updated, _ = prepare_page_references(page, manifest=V13_MANIFEST, bundle_root=BUNDLE, book_dir=book, mode="planning")
            updated["current_prompt_path"] = "prompt.md"
            updated["current_image_path"] = None
            updated["character_reference_assets"][0]["sha256"] = "0" * 64
            (book / "prompt.md").write_text("prompt\n", encoding="utf-8")
            (book / "story.md").write_text("story\n", encoding="utf-8")
            (book / "storyboard.json").write_text('{"pages":[{"page":1}]}', encoding="utf-8")
            (book / "layout.json").write_text('{"pages":[{"page":1}]}', encoding="utf-8")
            (book / "page-manifest.json").write_text(json.dumps({"age_band": "3-4", "pages": [updated]}, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                init_queue(book, book / "queue.json")


if __name__ == "__main__":
    unittest.main()

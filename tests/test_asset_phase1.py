"""Phase 1 asset catalog, reference contract, and cache-isolation tests."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class Phase1AssetTests(unittest.TestCase):
    def test_skill_package_contains_phase1_registries_and_generated_manifest_once(self):
        from package_skill import package_skill

        skill_dir = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "skill.zip"
            package_skill(skill_dir, output, "0.11.0-phase1")
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(names.count("make-kids-picturebooks/MANIFEST.json"), 1)
                for relative in (
                    "assets/style-registry.json",
                    "assets/scene-registry.json",
                    "assets/prop-registry.json",
                    "scripts/asset_catalog.py",
                ):
                    self.assertIn(f"make-kids-picturebooks/{relative}", names)

    def test_history_path_diagnostic_reports_nature_as_current_layout_ready(self):
        from diagnose_project_paths import diagnose_project_paths

        report = diagnose_project_paths(
            Path(r"D:\宝宝绘本制作\projects\nature-collector-3-4-v0.1"),
            "b01",
            "v0.1",
        )
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["story_page_count"], 11)
        self.assertEqual(report["missing_pages"], [])
        self.assertEqual(report["ambiguous_pages"], [])
        self.assertTrue(report["current_builder_search"][0]["current_builder_search"])

    def test_history_path_diagnostic_exposes_shadow_layout_mismatch_without_writing(self):
        from diagnose_project_paths import diagnose_project_paths

        report = diagnose_project_paths(
            Path(r"D:\宝宝绘本制作\projects\shadow-3-4-v1"),
            "b01",
            "v1",
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["missing_pages"], list(range(2, 13)))
        self.assertTrue(report["legacy_available"])
        self.assertEqual(report["write_operations"], 0)

    def test_style_registry_resolves_approved_alias_and_keeps_unreleased_style05_unapproved(self):
        from style_lock import load_style_master, load_style_registry, resolve_style_selection

        registry = load_style_registry()
        self.assertEqual(registry["schema_version"], 1)
        selection = resolve_style_selection("STYLE-01", mode="production")
        master = load_style_master()
        self.assertEqual(selection["canonical_id"], "STYLE-CORE-01")
        self.assertEqual(selection["version"], "v1.2")
        self.assertEqual(selection["content_hash"], master["content_hash"])
        self.assertEqual(resolve_style_selection("STYLE-CORE-01", mode="production")["canonical_id"], "STYLE-CORE-01")
        self.assertEqual(resolve_style_selection("STYLE-05", mode="planning")["status"], "candidate")
        with self.assertRaisesRegex(ValueError, "STYLE_NOT_APPROVED"):
            resolve_style_selection("STYLE-05", mode="production")
        style06 = resolve_style_selection("STYLE-06", mode="production")
        self.assertEqual(style06["status"], "approved")
        self.assertEqual(style06["version"], "v0.1")
        self.assertEqual(style06["reference_assets"][0]["reference_id"], "REF-STYLE-06-TRIO-01")
        with self.assertRaisesRegex(ValueError, "UNKNOWN_STYLE"):
            resolve_style_selection("STYLE-99", mode="planning")

    def test_character_reference_selection_is_traceable_without_fake_crop_coordinates(self):
        from asset_resolver import load_core_manifest, resolve_character_reference_selection
        from style_lock import APPROVED_REFERENCE_SHA256

        page = {
            "style_master_id": "STYLE-CORE-01",
            "style_master_version": "v1.2",
            "characters": [{
                "character_id": "CHAR-GIRL-01",
                "outfit_id": "G-01",
                "expression_id": "G-EX-02",
                "pose_id": "G-PO-01",
                "angle_id": "ANG-01",
            }],
        }
        selections = resolve_character_reference_selection(load_core_manifest(), page)
        self.assertTrue(selections)
        self.assertTrue({
            "reference_id", "character_id", "reference_file", "reference_hash",
            "reference_purpose", "reference_region", "style_binding", "validation_status",
        }.issubset(selections[0]))
        self.assertEqual(selections[0]["character_id"], "xiaoxiong")
        self.assertEqual(selections[0]["reference_hash"], APPROVED_REFERENCE_SHA256)
        self.assertEqual(selections[0]["validation_status"], "approved-reference")
        self.assertNotIn("crop_coordinates", selections[0])

    def test_scene_registry_is_metadata_only_and_candidate_is_not_production_ready(self):
        from asset_catalog import load_scene_registry, resolve_scene_ref

        registry = load_scene_registry()
        self.assertEqual({item["scene_id"] for item in registry["scenes"]}, {
            "SCENE-01", "SCENE-02", "SCENE-03", "SCENE-04",
        })
        resolved = resolve_scene_ref({"scene_id": "SCENE-01", "version": "v0.1"}, mode="planning")
        self.assertEqual(resolved["status"], "registered-unverified")
        self.assertEqual(resolved["reference_assets"], [])
        with self.assertRaisesRegex(ValueError, "SCENE_NOT_APPROVED"):
            resolve_scene_ref({"scene_id": "SCENE-01", "version": "v0.1"}, mode="production")

    def test_prop_registry_separates_identity_from_state_and_rejects_unknown_state(self):
        from asset_catalog import load_prop_registry, resolve_prop_ref

        registry = load_prop_registry()
        self.assertIn("PROP-BLOCK", {item["prop_id"] for item in registry["props"]})
        self.assertEqual(resolve_prop_ref({
            "asset_id": "PROP-BLOCK", "version": "v0.1", "state_id": "placed-on-floor",
        }, mode="planning")["prop_id"], "PROP-BLOCK")
        with self.assertRaisesRegex(ValueError, "INVALID_PROP_STATE"):
            resolve_prop_ref({
                "asset_id": "PROP-BLOCK", "version": "v0.1", "state_id": "unknown-state",
            }, mode="planning")
        with self.assertRaisesRegex(ValueError, "PROP_NOT_APPROVED"):
            resolve_prop_ref({
                "asset_id": "PROP-BLOCK", "version": "v0.1", "state_id": "placed-on-floor",
            }, mode="production")

    def test_page_asset_bindings_keep_legacy_props_and_reject_unapproved_new_refs(self):
        from asset_catalog import validate_page_asset_bindings

        legacy = {"props": [{"id": "blocks", "count": 3, "location": "floor", "state": "loose", "change": "introduced"}]}
        self.assertEqual(validate_page_asset_bindings(legacy, mode="production"), [])
        candidate = {
            "scene_ref": {"scene_id": "SCENE-01", "version": "v0.1"},
            "props": [{"asset_id": "PROP-BLOCK", "version": "v0.1", "state_id": "placed-on-floor"}],
        }
        errors = validate_page_asset_bindings(candidate, mode="production")
        self.assertIn("SCENE_NOT_APPROVED", errors)
        self.assertIn("PROP_NOT_APPROVED", errors)

    def test_optional_asset_fields_change_only_the_page_dependency_fingerprint(self):
        from page_versions import affected_pages, image_dependency_fingerprint

        before = [
            {"page_id": "PAGE-01", "page_version": "v1", "text": "a"},
            {"page_id": "PAGE-02", "page_version": "v1", "text": "b"},
        ]
        after = copy.deepcopy(before)
        after[0]["props"] = [{"asset_id": "PROP-BLOCK", "version": "v0.1", "state_id": "loose"}]
        self.assertNotEqual(image_dependency_fingerprint(before[0]), image_dependency_fingerprint(after[0]))
        self.assertEqual(affected_pages(before, after), {"image_redraw": ["PAGE-01"], "text_only": []})
        self.assertEqual(image_dependency_fingerprint(before[1]), image_dependency_fingerprint(after[1]))

    def test_old_page_without_optional_fields_keeps_legacy_fingerprint(self):
        from page_versions import image_dependency_fingerprint

        page = {
            "page_id": "PAGE-01",
            "page_version": "PAGE-01-v1",
            "character_asset_bundle": "core-characters-v1.2",
            "character_asset_version": "v1.2",
            "characters": [],
            "style_master_id": "STYLE-CORE-01",
            "style_master_version": "v1.2",
            "style_master_content_hash": "style-hash",
            "page_delta": {"scene": "yard"},
            "source_prompt_hash": "prompt-hash",
            "resolved_asset_hash": "asset-hash",
            "shot_id": "SHOT-WIDE-01",
            "interaction_id": None,
            "family_interaction_id": None,
        }
        legacy_payload = {
            field: page.get(field) for field in (
                "character_asset_bundle", "character_asset_version", "characters",
                "style_master_id", "style_master_version", "style_master_content_hash",
                "page_delta", "source_prompt_hash", "resolved_asset_hash", "shot_id",
                "interaction_id", "family_interaction_id",
            )
        }
        import hashlib

        expected = hashlib.sha256(json.dumps(
            legacy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertEqual(image_dependency_fingerprint(page), expected)


if __name__ == "__main__":
    unittest.main()

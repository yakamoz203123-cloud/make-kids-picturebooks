"""Focused adversarial coverage for the shipped asset-production bundle."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asset_resolver import CORE_BUNDLE_ROOT, load_aliases, load_core_manifest, reference_is_project_safe, resolve_character_alias, resolve_page_assets
from page_production import build_page_prompt, complete_page, validate_page_spec
from page_versions import affected_pages, image_dependency_fingerprint
from style_lock import load_style_master, style_content_hash, validate_style_master


class RealAssetProductionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_core_manifest()
        self.aliases = load_aliases()
        self.template = json.loads((ROOT / "assets" / "page-production-template.json").read_text(encoding="utf-8"))

    def test_template_is_a_valid_planning_record(self):
        self.assertEqual(validate_page_spec(self.template), [])
        self.assertIsNone(self.template["current_image_path"])
        self.assertEqual(self.template["profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(self.template["declared_aspect_ratio"], "3:4")
        self.assertTrue(build_page_prompt(self.template)["asset_selection"]["characters"])

    def test_template_metadata_is_required_once_production_record_is_selected(self):
        for field in ("text", "text_safe_area", "continuity", "source_prompt_hash", "resolved_asset_hash", "current_image_path", "review_status", "shot_id"):
            page = dict(self.template)
            page.pop(field)
            self.assertIn(field, validate_page_spec(page), field)

    def test_default_prompt_mode_rejects_compact_record_but_explicit_fixture_mode_accepts_it(self):
        compact = {key: value for key, value in self.template.items() if key not in {
            "text", "text_safe_area", "continuity", "source_prompt_hash", "resolved_asset_hash",
            "current_image_path", "review_status", "shot_id", "profile", "declared_aspect_ratio",
            "style_master_content_hash",
        }}
        with self.assertRaisesRegex(ValueError, "INVALID_PAGE_SPEC"):
            build_page_prompt(compact)
        self.assertTrue(build_page_prompt(compact, mode="fixture")["asset_selection"])

    def test_real_manifest_rejects_empty_unknown_and_invalid_interaction_bindings(self):
        for update, code in (({"characters": []}, "EMPTY_CHARACTERS"), ({"characters": [{**self.template["characters"][0], "outfit_id": "NOPE"}]}, "MISSING_ASSET"), ({"interaction_id": "NOT-REGISTERED"}, "MISSING_ASSET")):
            page = {**self.template, **update}
            self.assertEqual(resolve_page_assets(self.manifest, page, self.aliases)["failure"]["failure_code"], code)

    def test_interactions_must_support_every_resolved_character(self):
        mother = {**self.template, "characters": [{**self.template["characters"][0], "character_id": "CHAR-MOTHER-01", "outfit_id": "M-01", "expression_id": "M-EX-01", "pose_id": "M-PO-01"}], "interaction_id": "DUO-01"}
        self.assertEqual(resolve_page_assets(self.manifest, mother, self.aliases)["failure"]["failure_code"], "INCOMPATIBLE_ASSET")
        child = {**self.template, "family_interaction_id": "DUO-01"}
        self.assertEqual(resolve_page_assets(self.manifest, child, self.aliases)["failure"]["failure_code"], "INCOMPATIBLE_ASSET")
        self.assertEqual(resolve_page_assets(self.manifest, {**self.template, "interaction_id": "DUO-01"}, self.aliases)["failure"]["failure_code"], "INCOMPATIBLE_ASSET")
        family = {**self.template, "characters": [self.template["characters"][0], {"character_id": "CHAR-MOTHER-01", "outfit_id": "M-01", "expression_id": "M-EX-01", "pose_id": "M-PO-01", "angle_id": "ANG-01"}], "family_interaction_id": "PARENT-01"}
        self.assertTrue(resolve_page_assets(self.manifest, family, self.aliases)["ok"])

    def test_real_manifest_rejects_missing_reference_and_unapproved_metadata(self):
        for change, code in (({"visual_reference": {"reference_image": "missing.png"}}, "REFERENCE_NOT_FOUND"), ({"status": "draft"}, "ASSET_STATUS_NOT_APPROVED"), ({"version": "v9.9"}, "ASSET_VERSION_NOT_APPROVED")):
            manifest = {**self.manifest, **change}
            self.assertEqual(resolve_page_assets(manifest, self.template, self.aliases)["failure"]["failure_code"], code)

    def test_reference_path_conflict_and_alias_remap_fail_closed(self):
        conflict = copy.deepcopy(self.manifest)
        conflict["visual_reference"]["path"] = "reference/other.png"
        self.assertEqual(resolve_page_assets(conflict, self.template, self.aliases)["failure"]["failure_code"], "REFERENCE_NOT_FOUND")
        with self.assertRaisesRegex(ValueError, "ALIAS_NOT_APPROVED"):
            build_page_prompt(self.template, {**self.aliases, "CHAR-GIRL-01": "xiaomeng"})
        for overlay in ({"xiaoxiong": "xiaomeng"}, {"UNREGISTERED": "xiaoxiong"}):
            self.assertEqual(resolve_page_assets(self.manifest, self.template, overlay)["failure"]["failure_code"], "ALIAS_NOT_APPROVED")

    def test_public_alias_authority_rejects_canonical_remap(self):
        self.assertEqual(resolve_character_alias(self.manifest, "CHAR-GIRL-01", approved_aliases=self.aliases)["character_id"], "xiaoxiong")
        with self.assertRaisesRegex(ValueError, "ALIAS_NOT_APPROVED"):
            resolve_character_alias(self.manifest, "xiaoxiong", approved_aliases={"xiaoxiong": "xiaomeng"})

    def test_reference_bytes_are_verified_against_the_selected_bundle_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference" / "core-character-assets-v1.2.png"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"fake approved reference")
            self.assertFalse(reference_is_project_safe(self.manifest, root))
            self.assertEqual(resolve_page_assets(self.manifest, self.template, self.aliases, bundle_root=root)["failure"]["failure_code"], "REFERENCE_NOT_FOUND")

    def test_style_lock_rejects_non_reference_file_even_with_a_matching_hash(self):
        style = load_style_master()
        style["reference_image"] = "characters/core-v1.2/manifest.json"
        style["reference_sha256"] = "fd09ba52bfb75e46cfe2d60cba784af9835681d7703eef91092c27bb0487d090".upper()
        style["content_hash"] = style_content_hash(style)
        with self.assertRaisesRegex(ValueError, "INVALID_STYLE_MASTER"):
            build_page_prompt(self.template, style_master=style)

    def test_prompt_boundary_rejects_empty_manifest_and_tampered_style(self):
        with self.assertRaisesRegex(ValueError, "ASSET_STATUS_NOT_APPROVED"):
            build_page_prompt(self.template, manifest={})
        tampered = load_style_master()
        tampered["palette"] = ["tampered"]
        with self.assertRaisesRegex(ValueError, "INVALID_STYLE_MASTER"):
            build_page_prompt(self.template, style_master=tampered)
        selection = build_page_prompt(self.template)["asset_selection"]
        self.assertEqual(selection["style_master_content_hash"], load_style_master()["content_hash"])
        self.assertTrue(selection["resolved_asset_hash"])
        self.assertEqual(selection["manifest_content_hash"], self.manifest_content_hash())

    def test_prompt_boundary_rejects_rehashed_style_mutation(self):
        tampered = load_style_master()
        tampered["palette"] = ["tampered"]
        tampered["content_hash"] = style_content_hash(tampered)
        page = {**self.template, "style_master_content_hash": tampered["content_hash"]}
        with self.assertRaisesRegex(ValueError, "INVALID_STYLE_MASTER"):
            build_page_prompt(page, style_master=tampered)

    def test_selected_bundle_receipt_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "core-v1.2"
            shutil.copytree(CORE_BUNDLE_ROOT, bundle)
            receipt_path = bundle / "manifest-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["files"]["manifest.json"] = "0" * 64
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = resolve_page_assets(self.manifest, self.template, self.aliases, bundle_root=bundle)
            self.assertEqual(result["failure"]["failure_code"], "ASSET_MANIFEST_NOT_APPROVED")

    def test_prompt_boundary_rejects_non_object_manifest_without_loading_default(self):
        with self.assertRaisesRegex(ValueError, "ASSET_MANIFEST_NOT_APPROVED"):
            build_page_prompt(self.template, manifest=[])

    def test_resolver_production_mode_requires_complete_page_record(self):
        production_fields = {
            "production_schema", "text", "text_safe_area", "continuity", "source_prompt_hash",
            "resolved_asset_hash", "current_image_path", "review_status", "shot_id", "profile",
            "declared_aspect_ratio", "style_master_content_hash",
        }
        compact = {key: value for key, value in self.template.items() if key not in production_fields}
        result = resolve_page_assets(self.manifest, compact, self.aliases, mode="production")
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure"]["failure_code"], "INVALID_PAGE_SPEC")
        self.assertTrue(resolve_page_assets(self.manifest, compact, self.aliases, mode="fixture")["ok"])

    def manifest_content_hash(self):
        payload = json.dumps(self.manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def test_modified_selected_asset_definition_is_not_an_approved_manifest(self):
        mutated = copy.deepcopy(self.manifest)
        next(asset for asset in mutated["assets"] if asset["asset_id"] == "G-01")["description"] = "tampered"
        self.assertEqual(resolve_page_assets(mutated, self.template, self.aliases)["failure"]["failure_code"], "ASSET_MANIFEST_NOT_APPROVED")

    def test_style_lock_is_complete_and_tamper_evident(self):
        style = load_style_master()
        self.assertEqual(validate_style_master(style), [])
        changed = copy.deepcopy(style)
        changed["palette"].append("neon")
        self.assertIn("content_hash", validate_style_master(changed))

    def test_forged_header_is_not_an_image_and_declared_aspect_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            forged = Path(directory) / "forged.png"
            forged.write_bytes(b"\x89PNG\r\n\x1a\nnot a real image")
            with self.assertRaisesRegex(ValueError, "INVALID_IMAGE"):
                complete_page(self.template, forged)
            real = Path(directory) / "real.png"
            Image.new("RGB", (10, 10)).save(real)
            with self.assertRaisesRegex(ValueError, "INVALID_DIMENSIONS"):
                complete_page({**self.template, "fixture_policy": "allow-small-dimensions"}, real)
            with self.assertRaisesRegex(ValueError, "INVALID_DIMENSIONS"):
                complete_page(self.template, real)
            wrong_ratio = Path(directory) / "wrong-ratio.png"
            Image.new("RGB", (1440, 1600)).save(wrong_ratio)
            with self.assertRaisesRegex(ValueError, "ASPECT_RATIO_MISMATCH"):
                complete_page(self.template, wrong_ratio)

    def test_completion_accepts_native_profile_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            real = Path(directory) / "real.png"
            Image.new("RGB", (1080, 1440)).save(real)
            self.assertEqual(complete_page(self.template, real)["dimensions"], [1080, 1440])

    def test_image_dependency_changes_redraw_only_the_changed_page(self):
        before = [{**self.template, "page_id": "PAGE-01"}]
        after = [{**self.template, "page_id": "PAGE-01", "interaction_id": "DUO-01"}]
        self.assertNotEqual(image_dependency_fingerprint(before[0]), image_dependency_fingerprint(after[0]))
        self.assertEqual(affected_pages(before, after)["image_redraw"], ["PAGE-01"])
        self.assertNotEqual(image_dependency_fingerprint(before[0]), image_dependency_fingerprint({**before[0], "resolved_asset_hash": "changed"}))
        self.assertNotEqual(image_dependency_fingerprint(before[0]), image_dependency_fingerprint({**before[0], "style_master_content_hash": "changed"}))


if __name__ == "__main__":
    unittest.main()

"""RED-phase contracts for strict, asset-bound page production.

These tests intentionally describe the public contract for the next asset
production layer.  The fixture contains IDs and manifest metadata only; it
does not create or copy any visual assets.
"""

from __future__ import annotations

import json
import importlib
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LEGACY_PROMPT_PATH = Path(__file__).resolve().parent / "fixtures" / "legacy-page" / "prompt.md"
sys.path.insert(0, str(SCRIPTS))


CORE_MANIFEST = {
    "schema_version": 1,
    "bundle_id": "core-characters-v1.2",
    "version": "v1.2",
    "status": "approved-reference",
    "visual_reference": {
        "path": "reference/core-character-assets-v1.2.png",
        "reference_image": "reference/core-character-assets-v1.2.png",
    },
    "characters": [
        {
            "character_id": "xiaoxiong",
            "identity_asset_id": "G-ID-01",
            "default_outfit": "G-01",
            "version": "v1.2",
        },
        {
            "character_id": "xiaomeng",
            "identity_asset_id": "B-ID-01",
            "default_outfit": "B-01",
            "version": "v1.2",
        },
        {
            "character_id": "mother",
            "identity_asset_id": "M-ID-01",
            "default_outfit": "M-01",
            "version": "v1.2",
        },
    ],
    "assets": [
        {"asset_id": "G-ID-01", "character_id": "xiaoxiong", "asset_type": "identity", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "B-ID-01", "character_id": "xiaomeng", "asset_type": "identity", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "M-ID-01", "character_id": "mother", "asset_type": "identity", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "G-01", "character_id": "xiaoxiong", "asset_type": "outfit", "is_default": True, "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "B-01", "character_id": "xiaomeng", "asset_type": "outfit", "is_default": True, "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "M-01", "character_id": "mother", "asset_type": "outfit", "is_default": True, "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "G-EX-02", "character_id": "xiaoxiong", "asset_type": "expression", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "G-PO-01", "character_id": "xiaoxiong", "asset_type": "pose", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "ANG-01", "character_id": "shared", "asset_type": "angle", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
        {"asset_id": "STYLE-CORE-01", "character_id": "shared", "asset_type": "style", "version": "v1.2", "reference_image": "reference/core-character-assets-v1.2.png"},
    ],
}

ALIASES = {
    "CHAR-GIRL-01": "xiaoxiong",
    "CHAR-BOY-01": "xiaomeng",
    "CHAR-MOTHER-01": "mother",
}


def _page(**overrides):
    page = {
        "page_id": "PAGE-07",
        "page_version": "PAGE-07-v1",
        "story_version": "story-v1",
        "character_asset_bundle": "core-characters-v1.2",
        "character_asset_version": "v1.2",
        "characters": [
            {
                "character_id": "CHAR-GIRL-01",
                "outfit_id": "G-01",
                "expression_id": "G-EX-02",
                "pose_id": "G-PO-01",
                "angle_id": "ANG-01",
            }
        ],
        "style_master_id": "STYLE-CORE-01",
        "style_master_version": "v1.2",
        "page_delta": {"scene": "冰箱旁", "knowledge_evidence": "冰块边缘变圆"},
        "text": "冰块变小了。",
    }
    page.update(overrides)
    return page


class AssetProductionContractTests(unittest.TestCase):
    def _contract_function(self, module_name, function_name):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            self.fail(f"missing contract module {module_name}: {exc}")
        try:
            return getattr(module, function_name)
        except AttributeError as exc:
            self.fail(f"missing contract function {module_name}.{function_name}: {exc}")

    def test_v12_alias_registry_resolves_three_fixed_characters_and_defaults(self):
        resolve_character_alias = self._contract_function("asset_resolver", "resolve_character_alias")

        for alias, character_id in ALIASES.items():
            resolved = resolve_character_alias(CORE_MANIFEST, alias)
            expected_outfit = {
                "xiaoxiong": "G-01", "xiaomeng": "B-01", "mother": "M-01"
            }[character_id]
            self.assertEqual(
                resolved,
                {
                    "character_id": character_id,
                    "identity_asset_id": {
                        "xiaoxiong": "G-ID-01", "xiaomeng": "B-ID-01", "mother": "M-ID-01"
                    }[character_id],
                    "outfit_id": expected_outfit,
                    "bundle_id": "core-characters-v1.2",
                    "version": "v1.2",
                    "reference_image": "reference/core-character-assets-v1.2.png",
                },
            )

    def test_resolver_returns_explicit_codes_for_version_compatibility_and_missing_assets(self):
        resolve_page_assets = self._contract_function("asset_resolver", "resolve_page_assets")

        cases = (
            (CORE_MANIFEST, {"character_asset_version": "v9.9"}, "ASSET_VERSION_NOT_APPROVED"),
            (CORE_MANIFEST, {"characters": [{"character_id": "CHAR-GIRL-01", "outfit_id": "B-01"}]}, "INCOMPATIBLE_ASSET"),
            ({**CORE_MANIFEST, "visual_reference": {"reference_image": "missing.png"}}, {}, "REFERENCE_NOT_FOUND"),
            (CORE_MANIFEST, {"characters": [{"character_id": "CHAR-GIRL-01", "outfit_id": "G-99"}]}, "MISSING_ASSET"),
        )
        for manifest, change, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                result = resolve_page_assets(manifest, {**_page(), **change}, ALIASES, mode="fixture")
                self.assertFalse(result["ok"])
                self.assertEqual(result["failure"]["failure_code"], expected_code)

    def test_page_spec_requires_all_identity_and_style_bindings(self):
        validate_page_spec = self._contract_function("page_production", "validate_page_spec")

        self.assertEqual(validate_page_spec(_page(), mode="fixture"), [])
        required = ("character_id", "outfit_id", "expression_id", "pose_id", "angle_id")
        for field in required + ("style_master_id",):
            page = _page()
            if field == "style_master_id":
                page.pop(field)
            else:
                page["characters"][0].pop(field)
            with self.subTest(field=field):
                self.assertIn(field, validate_page_spec(page, mode="fixture"))

        empty_bindings = (
            ("character_asset_bundle", lambda page: page.update(character_asset_bundle="")),
            ("character_asset_version", lambda page: page.update(character_asset_version="")),
            ("character_id", lambda page: page["characters"][0].update(character_id="")),
            ("outfit_id", lambda page: page["characters"][0].update(outfit_id="")),
            ("expression_id", lambda page: page["characters"][0].update(expression_id="")),
            ("pose_id", lambda page: page["characters"][0].update(pose_id="")),
            ("angle_id", lambda page: page["characters"][0].update(angle_id="")),
            ("style_master_id", lambda page: page.update(style_master_id="")),
            ("style_master_version", lambda page: page.update(style_master_version="")),
        )
        for field, invalidate in empty_bindings:
            page = _page()
            invalidate(page)
            with self.subTest(empty_field=field):
                errors = validate_page_spec(page, mode="fixture")
                self.assertTrue(any(field in str(error) for error in errors), errors)

        for field, invalidate in (
            ("character_asset_version", lambda page: page.update(character_asset_version="v9.9")),
            ("style_master_version", lambda page: page.update(style_master_version="v9.9")),
        ):
            page = _page()
            invalidate(page)
            with self.subTest(invalid_version_field=field):
                errors = validate_page_spec(page, mode="fixture")
                self.assertTrue(any(field in str(error) and "version" in str(error) for error in errors), errors)

    def test_prompt_contract_accepts_only_asset_selection_and_page_delta(self):
        build_page_prompt = self._contract_function("page_production", "build_page_prompt")
        validate_page_spec = self._contract_function("page_production", "validate_page_spec")

        prompt = build_page_prompt(_page(), mode="fixture")
        self.assertEqual(set(prompt), {"asset_selection", "page_delta"})
        self.assertEqual(prompt["asset_selection"]["bundle_id"], "core-characters-v1.2")
        self.assertEqual(prompt["asset_selection"]["version"], "v1.2")
        self.assertEqual(prompt["asset_selection"]["characters"][0]["character_id"], "xiaoxiong")
        self.assertEqual(prompt["asset_selection"]["characters"][0]["identity_asset_id"], "G-ID-01")
        self.assertEqual(prompt["asset_selection"]["characters"][0]["outfit_id"], "G-01")
        self.assertEqual(prompt["page_delta"], _page()["page_delta"])
        invalid = _page()
        invalid["characters"][0].pop("pose_id")
        self.assertTrue(validate_page_spec(invalid, mode="fixture"))

    def test_page_version_change_invalidates_only_target_page_and_text_edit_does_not_redraw(self):
        affected_pages = self._contract_function("page_versions", "affected_pages")

        before = [_page(page_id="PAGE-07"), _page(page_id="PAGE-08", page_version="PAGE-08-v1")]
        after = [
            _page(page_id="PAGE-07", page_version="PAGE-07-v2"),
            _page(page_id="PAGE-08", page_version="PAGE-08-v1", text="文字小修。"),
        ]
        result = affected_pages(before, after)
        self.assertEqual(result["image_redraw"], ["PAGE-07"])
        self.assertEqual(result["text_only"], ["PAGE-08"])

    def test_invalid_image_cannot_transition_to_completed(self):
        complete_page = self._contract_function("page_production", "complete_page")

        with self.assertRaisesRegex(ValueError, "INVALID_IMAGE"):
            complete_page(_page(), "not-an-image.png", mode="fixture")

    def test_legacy_schema_v1_page_still_passes_legacy_validation(self):
        validate_legacy_page = self._contract_function("page_production", "validate_legacy_page")

        self.assertTrue(LEGACY_PROMPT_PATH.is_file())
        self.assertEqual(LEGACY_PROMPT_PATH.read_text(encoding="utf-8"), "A child observes three blocks on the floor.\n")
        legacy = {
            "schema_version": 1,
            "book_id": "b01",
            "age_band": "3-4",
            "pages": [{
                "page": 1,
                "text_version": "v1",
                "characters_version": "test-v1",
                "current_prompt_path": "fixtures/legacy-page/prompt.md",
                "current_image_path": None,
                "text_area": [10, 110, 120, 80],
                "props": [{"id": "blocks", "count": 3, "location": "floor", "state": "loose", "change": "introduced"}],
                "knowledge_check": {"status": "pending", "evidence": ""},
            }],
        }
        self.assertEqual(validate_legacy_page(legacy), [])

    def test_failure_event_has_code_page_revision_and_recovery_advice(self):
        failure_event = self._contract_function("page_production", "failure_event")

        event = failure_event("MISSING_ASSET", page_id="PAGE-07", revision=2)
        self.assertEqual(event["failure_code"], "MISSING_ASSET")
        self.assertEqual(event["page_id"], "PAGE-07")
        self.assertEqual(event["revision"], 2)
        self.assertTrue(event["recovery_advice"])

    def test_style_master_change_invalidates_dependent_pages(self):
        affected_pages_for_style_change = self._contract_function(
            "style_lock", "affected_pages_for_style_change"
        )

        pages = [
            _page(page_id="PAGE-07", style_master_id="STYLE-CORE-01"),
            _page(page_id="PAGE-08", style_master_id="STYLE-OTHER-01"),
        ]
        self.assertEqual(
            affected_pages_for_style_change(pages, "STYLE-CORE-01", "STYLE-CORE-02"),
            ["PAGE-07"],
        )

    def test_asset_manifest_is_serializable_and_traceable_to_reference_and_versions(self):
        serialize_asset_manifest = self._contract_function("asset_resolver", "serialize_asset_manifest")

        serialized = serialize_asset_manifest(CORE_MANIFEST)
        loaded = json.loads(serialized)
        self.assertEqual(loaded["bundle_id"], "core-characters-v1.2")
        self.assertEqual(loaded["version"], "v1.2")
        self.assertEqual(loaded["visual_reference"]["reference_image"], "reference/core-character-assets-v1.2.png")
        self.assertEqual(loaded, CORE_MANIFEST)
        self.assertTrue(all(asset["reference_image"] == loaded["visual_reference"]["reference_image"] for asset in loaded["assets"]))
        self.assertTrue(all(asset["version"] == loaded["version"] for asset in loaded["assets"]))


if __name__ == "__main__":
    unittest.main()

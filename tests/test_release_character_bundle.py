"""Isolated tests for the Phase 2G character-bundle release entry."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asset_resolver import load_core_manifest, resolve_page_assets
from release_character_bundle import (
    APPROVED_REFERENCE_IDS,
    commit_release,
    file_hash,
    main,
    prepare_release,
    verify_published_bundle,
)


PHASE2E = Path(r"D:\宝宝绘本制作\projects\character-assets-phase2e-2026-10-19")
BUNDLE = PHASE2E / "staged-assets" / "core-v1.3"
V12_ROOT = ROOT / "assets" / "characters" / "core-v1.2"


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def refresh_staged_receipt(bundle: Path) -> None:
    """Refresh only the staged receipt inside an isolated test fixture."""
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {
        path.relative_to(bundle).as_posix(): file_hash(path)
        for path in sorted(bundle.rglob("*"))
        if path.is_file() and path.name != "manifest-receipt.json"
    }
    receipt = {
        "schema_version": 1,
        "bundle_id": manifest["bundle_id"],
        "version": manifest["version"],
        "status": "staged",
        "release_status": "pending_approval",
        "immutable": False,
        "manifest_sha256": canonical_hash(manifest),
        "manifest_bytes_sha256": file_hash(manifest_path),
        "reference_image": manifest["visual_reference"]["reference_image"],
        "reference_sha256": manifest["visual_reference"]["reference_sha256"],
        "files": files,
    }
    receipt["receipt_sha256"] = canonical_hash(receipt)
    (bundle / "manifest-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class ReleaseCharacterBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="phase2g-release-test-")
        self.root = Path(self.tmp.name)
        self.candidate = self.root / "candidate" / "core-v1.3"
        shutil.copytree(BUNDLE, self.candidate)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_formally_approved_fixture(self, *, isolated_formal_shape: bool = False) -> Path:
        approval_path = self.candidate / "approval.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["formal_production_approval"] = {
            "status": "approved",
            "approval_source": "explicit_user_confirmation" if isolated_formal_shape else "isolated_test_fixture",
            "evidence_id": "TEST-FIXTURE-PHASE2G-001",
            "recorded_at": "2026-10-19",
        }
        if not isolated_formal_shape:
            approval["formal_production_approval"]["test_fixture"] = True
        for item in approval["assets"]:
            if item["asset_id"] in APPROVED_REFERENCE_IDS:
                item["approved_for_production"] = True
                item["production_approval"] = {
                    "status": "approved",
                    "approval_source": "explicit_user_confirmation" if isolated_formal_shape else "isolated_test_fixture",
                    "evidence_id": f"TEST-FIXTURE-{item['asset_id']}",
                    "recorded_at": "2026-10-19",
                }
                if not isolated_formal_shape:
                    item["production_approval"]["test_fixture"] = True
        approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        refresh_staged_receipt(self.candidate)
        return self.candidate

    @staticmethod
    def assert_error(result: dict, code: str) -> None:
        if result.get("ok"):
            raise AssertionError(f"expected {code}, got success: {result}")
        if code not in result.get("error_codes", []):
            raise AssertionError(f"expected {code}, got {result.get('error_codes')}: {result}")

    def test_real_v13_has_approval_but_remains_staged(self):
        result = prepare_release(BUNDLE)
        self.assertTrue(result["ok"], result)
        manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "staged")
        self.assertEqual(manifest["release_status"], "pending_approval")
        self.assertFalse(manifest["production_enabled"])

    def test_prepare_cli_returns_success_for_staged_real_v13_with_valid_approval(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["prepare", "--bundle", str(BUNDLE)])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["mode"], "prepare")

    def test_visual_approval_without_production_approval_fails(self):
        approval = json.loads((self.candidate / "approval.json").read_text(encoding="utf-8"))
        self.assertTrue(all(item["visual_review_status"] == "user_approved" for item in approval["assets"]))
        approval.pop("formal_production_approval", None)
        (self.candidate / "approval.json").write_text(
            json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        refresh_staged_receipt(self.candidate)
        result = prepare_release(self.candidate)
        self.assert_error(result, "PRODUCTION_APPROVAL_MISSING")

    def test_reference_hash_mismatch_fails(self):
        reference = self.candidate / "reference" / "xiaoxiong-fullbody-v2.png"
        reference.write_bytes(reference.read_bytes() + b"tamper")
        result = prepare_release(self.candidate)
        self.assert_error(result, "REFERENCE_HASH_MISMATCH")

    def test_missing_reference_fails(self):
        (self.candidate / "reference" / "mother-fullbody-v1.png").unlink()
        result = prepare_release(self.candidate)
        self.assert_error(result, "REFERENCE_MISSING")

    def test_reference_path_escape_fails(self):
        sources_path = self.candidate / "asset-sources.json"
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        sources["assets"][0]["path"] = "../outside.png"
        sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        refresh_staged_receipt(self.candidate)
        result = prepare_release(self.candidate)
        self.assert_error(result, "REFERENCE_PATH_UNSAFE")

    def test_staged_receipt_cannot_masquerade_as_formal_receipt(self):
        result = verify_published_bundle(BUNDLE)
        self.assert_error(result, "FORMAL_RECEIPT_REQUIRED")

    def test_version_conflict_fails_before_overwrite(self):
        candidate = self.make_formally_approved_fixture()
        destination = self.root / "published" / "core-v1.3"
        first = commit_release(candidate, destination, simulation=True)
        self.assertTrue(first["ok"], first)
        before = file_hash(destination / "manifest-receipt.json")
        second = commit_release(candidate, destination, simulation=True)
        self.assert_error(second, "RELEASE_TARGET_EXISTS")
        self.assertEqual(file_hash(destination / "manifest-receipt.json"), before)

    def test_complete_test_fixture_can_be_simulated_and_receipt_validates(self):
        candidate = self.make_formally_approved_fixture()
        destination = self.root / "published" / "core-v1.3"
        result = commit_release(candidate, destination, simulation=True)
        self.assertTrue(result["ok"], result)
        self.assertTrue((destination / "manifest-receipt.json").is_file())
        verified = verify_published_bundle(destination)
        self.assertTrue(verified["ok"], verified)
        receipt = json.loads((destination / "manifest-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "released")
        self.assertTrue(receipt["immutable"])
        self.assertNotEqual(receipt["receipt_sha256"], json.loads((candidate / "manifest-receipt.json").read_text(encoding="utf-8"))["receipt_sha256"])

    def test_failed_commit_preserves_existing_version(self):
        candidate = self.make_formally_approved_fixture()
        published_root = self.root / "published"
        old_version = published_root / "core-v1.2"
        old_version.mkdir(parents=True)
        (old_version / "keep.txt").write_text("old-release", encoding="utf-8")
        destination = published_root / "core-v1.3"
        with mock.patch("release_character_bundle.os.replace", side_effect=OSError("simulated switch failure")):
            result = commit_release(candidate, destination, simulation=True)
        self.assert_error(result, "COMMIT_FAILED")
        self.assertTrue((old_version / "keep.txt").is_file())
        self.assertFalse(destination.exists())

    def test_v12_production_chain_still_resolves(self):
        manifest = load_core_manifest()
        self.assertEqual(manifest["bundle_id"], "core-characters-v1.2")
        self.assertEqual(manifest["status"], "approved-reference")
        receipt = json.loads((V12_ROOT / "manifest-receipt.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt["immutable"])

    def test_simulated_release_cannot_masquerade_as_production(self):
        candidate = self.make_formally_approved_fixture()
        destination = self.root / "published" / "core-v1.3"
        committed = commit_release(candidate, destination, simulation=True)
        self.assertTrue(committed["ok"], committed)
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        page = json.loads((ROOT / "assets" / "page-production-template.json").read_text(encoding="utf-8"))
        page.update(
            characters=[{"character_id": "CHAR-GIRL-01", "outfit_id": "G-01", "expression_id": "G-EX-02", "pose_id": "G-PO-01", "angle_id": "ANG-01"}],
            character_asset_bundle="core-characters-v1.3",
            character_asset_version="v1.3",
            characters_version="v1.3",
        )
        resolved = resolve_page_assets(manifest, page, bundle_root=destination, mode="production")
        self.assertFalse(resolved["ok"])
        self.assertEqual(resolved["failure"]["failure_code"], "ASSET_MANIFEST_NOT_APPROVED")

    def test_isolated_formal_shape_is_accepted_by_production_resolver(self):
        # This synthetic approval record exists only in the TemporaryDirectory;
        # it is never copied into the real staged bundle or production tree.
        candidate = self.make_formally_approved_fixture(isolated_formal_shape=True)
        destination = self.root / "published" / "core-v1.3-formal-shape"
        committed = commit_release(candidate, destination, simulation=False)
        self.assertTrue(committed["ok"], committed)
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        page = json.loads((ROOT / "assets" / "page-production-template.json").read_text(encoding="utf-8"))
        page.update(
            characters=[{"character_id": "CHAR-GIRL-01", "outfit_id": "G-01", "expression_id": "G-EX-02", "pose_id": "G-PO-01", "angle_id": "ANG-01"}],
            character_asset_bundle="core-characters-v1.3",
            character_asset_version="v1.3",
            characters_version="v1.3",
        )
        resolved = resolve_page_assets(manifest, page, bundle_root=destination, mode="production")
        self.assertTrue(resolved["ok"], resolved)

    def test_real_v13_production_gate_remains_closed(self):
        manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        page = json.loads((ROOT / "assets" / "page-production-template.json").read_text(encoding="utf-8"))
        page.update(
            characters=[{"character_id": "CHAR-GIRL-01", "outfit_id": "G-01", "expression_id": "G-EX-02", "pose_id": "G-PO-01", "angle_id": "ANG-01"}],
            character_asset_bundle="core-characters-v1.3",
            character_asset_version="v1.3",
            characters_version="v1.3",
        )
        result = resolve_page_assets(manifest, page, bundle_root=BUNDLE, mode="production")
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure"]["failure_code"], "ASSET_STATUS_NOT_APPROVED")

    def test_release_module_has_no_image_generation_dependency(self):
        source = (ROOT / "scripts" / "release_character_bundle.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("imagegen", source)
        self.assertNotIn("image_gen", source)
        self.assertNotIn("openai", source)

    def test_real_bundle_and_fixture_are_isolated(self):
        candidate = self.make_formally_approved_fixture()
        self.assertNotEqual(file_hash(candidate / "approval.json"), file_hash(BUNDLE / "approval.json"))
        self.assertEqual(file_hash(BUNDLE / "manifest.json"), file_hash(PHASE2E / "staged-assets" / "core-v1.3" / "manifest.json"))


if __name__ == "__main__":
    unittest.main()

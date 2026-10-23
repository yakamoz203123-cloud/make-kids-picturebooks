"""Safe two-stage release entry for reusable character bundles.

This module deliberately does not publish a bundle by changing approval flags.  A
candidate must already contain independent production-approval evidence.  The
commit operation copies the candidate into an isolated temporary snapshot,
derives a new formal receipt from that final snapshot, verifies it, and only then
switches the destination into place.  ``simulation=True`` is reserved for
explicitly marked isolated test fixtures and never changes the source bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


APPROVED_REFERENCE_IDS = (
    "G-ID-01",
    "B-ID-01",
    "M-ID-01",
    "G-ACT-A-01",
    "G-ACT-B-01",
    "GROUP-REF-01",
)
FORMAL_RECEIPT_TYPE = "formal-character-bundle-release"
STAGED_RECEIPT_STATUS = ("staged", "pending_approval", False)
FORMAL_RELEASE_STATUS = ("released", "released", True)


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _error(result: dict[str, Any], code: str, detail: str) -> None:
    if code not in result["error_codes"]:
        result["error_codes"].append(code)
    result["errors"].append({"code": code, "detail": detail})


def _result(mode: str, bundle_root: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "bundle_root": str(bundle_root),
        "error_codes": [],
        "errors": [],
        "warnings": [],
    }


def _files_hashes(bundle_root: Path) -> dict[str, str]:
    return {
        path.relative_to(bundle_root).as_posix(): file_hash(path)
        for path in sorted(bundle_root.rglob("*"))
        if path.is_file() and path.name != "manifest-receipt.json"
    }


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _validate_reference_files(
    bundle_root: Path,
    manifest: dict[str, Any],
    sources: dict[str, Any],
    result: dict[str, Any],
) -> None:
    source_assets = sources.get("assets") if isinstance(sources.get("assets"), list) else []
    source_by_id = {item.get("asset_id"): item for item in source_assets if isinstance(item, dict)}
    if set(source_by_id) != set(APPROVED_REFERENCE_IDS):
        _error(result, "UNKNOWN_SOURCE_ASSET", "asset-sources.json must contain exactly the six approved reference IDs")

    manifest_by_id = {
        item.get("asset_id"): item
        for item in manifest.get("assets", [])
        if isinstance(item, dict)
    }
    for asset_id in APPROVED_REFERENCE_IDS:
        source = source_by_id.get(asset_id)
        if not source:
            continue
        relative = source.get("path")
        expected = source.get("sha256")
        if not _safe_relative_path(relative):
            _error(result, "REFERENCE_PATH_UNSAFE", f"{asset_id} reference path must stay inside the bundle")
            continue
        path = bundle_root / relative
        if not path.is_file():
            _error(result, "REFERENCE_MISSING", f"{asset_id} reference is missing: {relative}")
            continue
        if not isinstance(expected, str) or file_hash(path) != expected:
            _error(result, "REFERENCE_HASH_MISMATCH", f"{asset_id} reference hash does not match asset-sources.json")
        manifest_asset = manifest_by_id.get(asset_id)
        if not manifest_asset or manifest_asset.get("reference_image") != relative:
            _error(result, "MANIFEST_SOURCE_MISMATCH", f"manifest reference mapping does not match {asset_id}")
        if not source.get("source_path") or not source.get("role"):
            _error(result, "UNKNOWN_SOURCE_ASSET", f"{asset_id} is missing source provenance")

    visual = manifest.get("visual_reference") if isinstance(manifest.get("visual_reference"), dict) else {}
    visual_relative = visual.get("reference_image")
    visual_expected = visual.get("reference_sha256")
    visual_path = bundle_root / visual_relative if isinstance(visual_relative, str) else None
    if not _safe_relative_path(visual_relative):
        _error(result, "REFERENCE_PATH_UNSAFE", "manifest visual reference path must stay inside the bundle")
    elif visual_path is None or not visual_path.is_file():
        _error(result, "REFERENCE_MISSING", "manifest visual reference is missing")
    elif not isinstance(visual_expected, str) or file_hash(visual_path) != visual_expected:
        _error(result, "REFERENCE_HASH_MISMATCH", "manifest visual reference hash does not match")


def _validate_visual_and_production_approval(
    approval: dict[str, Any],
    result: dict[str, Any],
    *,
    simulation: bool,
) -> None:
    confirmation = approval.get("user_visual_confirmation")
    approved_ids = set(confirmation.get("approved_asset_ids", [])) if isinstance(confirmation, dict) else set()
    if approved_ids != set(APPROVED_REFERENCE_IDS):
        _error(result, "VISUAL_APPROVAL_MISSING", "visual confirmation does not cover exactly the six required references")

    assets = approval.get("assets") if isinstance(approval.get("assets"), list) else []
    by_id = {item.get("asset_id"): item for item in assets if isinstance(item, dict)}
    for asset_id in APPROVED_REFERENCE_IDS:
        item = by_id.get(asset_id)
        if not item or item.get("visual_review_status") != "user_approved":
            _error(result, "VISUAL_APPROVAL_MISSING", f"visual approval is missing for {asset_id}")

    mother = by_id.get("M-ID-01", {})
    low_confidence = mother.get("low_confidence_detail")
    if not isinstance(low_confidence, dict) or low_confidence.get("field") != "waist_tie_structure" or low_confidence.get("status") != "low_confidence":
        _error(result, "LOW_CONFIDENCE_DETAIL_MISSING", "M-ID-01 must preserve the low-confidence waist-tie constraint")

    formal = approval.get("formal_production_approval")
    if not isinstance(formal, dict) or formal.get("status") != "approved":
        _error(result, "PRODUCTION_APPROVAL_MISSING", "independent formal production approval record is absent")
        return
    if formal.get("test_fixture") and not simulation:
        _error(result, "TEST_FIXTURE_APPROVAL_NOT_ALLOWED", "test-fixture approval cannot be used for a real release")
    for asset_id in APPROVED_REFERENCE_IDS:
        item = by_id.get(asset_id, {})
        production = item.get("production_approval")
        required = ("approval_source", "evidence_id", "recorded_at")
        if item.get("approved_for_production") is not True or not isinstance(production, dict) or production.get("status") != "approved" or any(not production.get(field) for field in required):
            _error(result, "PRODUCTION_APPROVAL_MISSING", f"independent production approval is missing for {asset_id}")
            continue
        if production.get("test_fixture") and not simulation:
            _error(result, "TEST_FIXTURE_APPROVAL_NOT_ALLOWED", f"test-fixture approval cannot release {asset_id}")
        if not simulation and production.get("approval_source") != "explicit_user_confirmation":
            _error(result, "PRODUCTION_APPROVAL_SOURCE_INVALID", f"production approval source is not explicit user evidence for {asset_id}")


def _validate_staged_receipt(
    bundle_root: Path,
    manifest: dict[str, Any],
    result: dict[str, Any],
) -> None:
    receipt_path = bundle_root / "manifest-receipt.json"
    if not receipt_path.is_file():
        _error(result, "STAGED_RECEIPT_MISSING", "candidate has no staged receipt")
        return
    try:
        receipt = _json(receipt_path)
    except Exception as exc:  # pragma: no cover - defensive parse boundary
        _error(result, "STAGED_RECEIPT_INVALID", f"cannot parse staged receipt: {exc}")
        return
    if (receipt.get("status"), receipt.get("release_status"), receipt.get("immutable")) != STAGED_RECEIPT_STATUS:
        _error(result, "FORMAL_RECEIPT_NOT_ALLOWED", "candidate receipt is not the expected non-formal staged receipt")
        return
    if receipt.get("bundle_id") != manifest.get("bundle_id") or receipt.get("version") != manifest.get("version"):
        _error(result, "STAGED_RECEIPT_INVALID", "staged receipt identity does not match manifest")
    expected_files = _files_hashes(bundle_root)
    if receipt.get("files") != expected_files:
        _error(result, "STAGED_RECEIPT_INVALID", "staged receipt file hashes do not match candidate contents")
    manifest_path = bundle_root / "manifest.json"
    if receipt.get("manifest_sha256") != canonical_hash(manifest) or receipt.get("manifest_bytes_sha256") != file_hash(manifest_path):
        _error(result, "STAGED_RECEIPT_INVALID", "staged receipt manifest hashes do not match candidate")
    if receipt.get("receipt_sha256") != canonical_hash({k: v for k, v in receipt.items() if k != "receipt_sha256"}):
        _error(result, "STAGED_RECEIPT_INVALID", "staged receipt self-hash is invalid")


def validate_candidate(
    bundle_root: Path,
    *,
    expected_bundle_id: str = "core-characters-v1.3",
    expected_version: str = "v1.3",
    simulation: bool = False,
) -> dict[str, Any]:
    """Validate a staged candidate without changing any file."""
    bundle_root = Path(bundle_root)
    result = _result("validate", bundle_root)
    required = ("manifest.json", "approval.json", "asset-sources.json", "manifest-receipt.json")
    missing = [name for name in required if not (bundle_root / name).is_file()]
    for name in missing:
        _error(result, "RELEASE_FILE_MISSING", f"required release file is missing: {name}")
    if missing:
        result["ok"] = False
        return result

    try:
        manifest = _json(bundle_root / "manifest.json")
        approval = _json(bundle_root / "approval.json")
        sources = _json(bundle_root / "asset-sources.json")
    except Exception as exc:  # pragma: no cover - defensive parse boundary
        _error(result, "RELEASE_JSON_INVALID", str(exc))
        result["ok"] = False
        return result

    result.update(bundle_id=manifest.get("bundle_id"), version=manifest.get("version"))
    if manifest.get("bundle_id") != expected_bundle_id or approval.get("bundle_id") != expected_bundle_id or sources.get("bundle_id") != expected_bundle_id:
        _error(result, "BUNDLE_ID_MISMATCH", "manifest, approval, and source registry bundle IDs must match the release target")
    if manifest.get("version") != expected_version or approval.get("version") != expected_version:
        _error(result, "VERSION_MISMATCH", "manifest and approval versions must match the release target")
    if manifest.get("status") != "staged" or manifest.get("release_status") != "pending_approval" or manifest.get("production_enabled") is not False:
        _error(result, "CANDIDATE_STATE_INVALID", "release input must remain staged, pending approval, and production-disabled")
    if approval.get("release_status") != "pending_approval" or approval.get("production_enabled") is not False:
        _error(result, "APPROVAL_STATE_INVALID", "approval record must remain pending and production-disabled before commit")
    if manifest.get("approval_registry") != "approval.json":
        _error(result, "MANIFEST_APPROVAL_MISMATCH", "manifest approval_registry must point to approval.json")
    encoded = json.dumps(manifest, ensure_ascii=False)
    if "STYLE-05" in encoded or "STYLE-06" in encoded:
        _error(result, "STYLE_BINDING_INVALID", "candidate contains a forbidden STYLE-05 or STYLE-06 binding")
    style_assets = [item for item in manifest.get("assets", []) if isinstance(item, dict) and item.get("asset_id") == "STYLE-CORE-01"]
    if len(style_assets) != 1 or style_assets[0].get("style_master_version") != "v1.2":
        _error(result, "STYLE_BINDING_INVALID", "candidate must bind exactly to STYLE-CORE-01 v1.2")
    if approval.get("bundle_id") != manifest.get("bundle_id") or approval.get("version") != manifest.get("version"):
        _error(result, "MANIFEST_APPROVAL_MISMATCH", "approval identity does not match manifest")

    _validate_reference_files(bundle_root, manifest, sources, result)
    _validate_visual_and_production_approval(approval, result, simulation=simulation)
    _validate_staged_receipt(bundle_root, manifest, result)
    result["ok"] = not result["error_codes"]
    return result


def prepare_release(bundle_root: Path, **kwargs: Any) -> dict[str, Any]:
    """Run the release preflight; this function is read-only."""
    result = validate_candidate(bundle_root, **kwargs)
    result["mode"] = "prepare"
    result["mutated_source"] = False
    return result


def _formal_receipt(bundle_root: Path, manifest: dict[str, Any], approval: dict[str, Any], *, simulation: bool) -> dict[str, Any]:
    files = _files_hashes(bundle_root)
    manifest_path = bundle_root / "manifest.json"
    approval_path = bundle_root / "approval.json"
    manifest_sha = canonical_hash(manifest)
    approval_sha = canonical_hash(approval)
    content_sha = canonical_hash({
        "bundle_id": manifest["bundle_id"],
        "version": manifest["version"],
        "manifest_sha256": manifest_sha,
        "approval_sha256": approval_sha,
        "files": files,
    })
    receipt = {
        "schema_version": 1,
        "receipt_type": FORMAL_RECEIPT_TYPE,
        "bundle_id": manifest["bundle_id"],
        "version": manifest["version"],
        "status": "released",
        "release_status": "released",
        "immutable": True,
        "simulation": bool(simulation),
        "manifest_sha256": manifest_sha,
        "manifest_bytes_sha256": file_hash(manifest_path),
        "approval_sha256": approval_sha,
        "approval_bytes_sha256": file_hash(approval_path),
        "reference_image": manifest["visual_reference"]["reference_image"],
        "reference_sha256": manifest["visual_reference"]["reference_sha256"],
        "files": files,
        "content_sha256": content_sha,
    }
    receipt["receipt_sha256"] = canonical_hash(receipt)
    return receipt


def verify_published_bundle(
    bundle_root: Path,
    *,
    expected_bundle_id: str = "core-characters-v1.3",
    expected_version: str = "v1.3",
) -> dict[str, Any]:
    """Verify a final release snapshot and its formal receipt."""
    bundle_root = Path(bundle_root)
    result = _result("verify", bundle_root)
    required = ("manifest.json", "approval.json", "asset-sources.json", "manifest-receipt.json")
    missing = [name for name in required if not (bundle_root / name).is_file()]
    for name in missing:
        _error(result, "RELEASE_FILE_MISSING", f"published bundle file is missing: {name}")
    if missing:
        result["ok"] = False
        return result
    try:
        manifest = _json(bundle_root / "manifest.json")
        approval = _json(bundle_root / "approval.json")
        sources = _json(bundle_root / "asset-sources.json")
        receipt = _json(bundle_root / "manifest-receipt.json")
    except Exception as exc:  # pragma: no cover - defensive parse boundary
        _error(result, "RELEASE_JSON_INVALID", str(exc))
        result["ok"] = False
        return result

    result.update(bundle_id=manifest.get("bundle_id"), version=manifest.get("version"), simulation=bool(receipt.get("simulation")))
    if manifest.get("bundle_id") != expected_bundle_id or manifest.get("version") != expected_version:
        _error(result, "BUNDLE_ID_VERSION_MISMATCH", "published manifest does not match expected release")
    if manifest.get("status") != "approved-reference" or manifest.get("release_status") != "released" or manifest.get("production_enabled") is not True:
        _error(result, "PUBLISHED_STATE_INVALID", "published manifest is not in the released production state")
    if (receipt.get("receipt_type"), receipt.get("status"), receipt.get("release_status"), receipt.get("immutable")) != (FORMAL_RECEIPT_TYPE, "released", "released", True):
        _error(result, "FORMAL_RECEIPT_REQUIRED", "published bundle must contain a formal immutable release receipt")
    if receipt.get("bundle_id") != manifest.get("bundle_id") or receipt.get("version") != manifest.get("version"):
        _error(result, "RECEIPT_IDENTITY_MISMATCH", "formal receipt identity does not match manifest")
    expected_files = _files_hashes(bundle_root)
    if receipt.get("files") != expected_files:
        _error(result, "RECEIPT_FILE_HASH_MISMATCH", "formal receipt file hashes do not match published contents")
    manifest_path = bundle_root / "manifest.json"
    approval_path = bundle_root / "approval.json"
    if receipt.get("manifest_sha256") != canonical_hash(manifest) or receipt.get("manifest_bytes_sha256") != file_hash(manifest_path):
        _error(result, "RECEIPT_MANIFEST_HASH_MISMATCH", "formal receipt manifest hashes do not match")
    if receipt.get("approval_sha256") != canonical_hash(approval) or receipt.get("approval_bytes_sha256") != file_hash(approval_path):
        _error(result, "RECEIPT_APPROVAL_HASH_MISMATCH", "formal receipt approval hashes do not match")
    expected_content = canonical_hash({
        "bundle_id": manifest.get("bundle_id"),
        "version": manifest.get("version"),
        "manifest_sha256": canonical_hash(manifest),
        "approval_sha256": canonical_hash(approval),
        "files": expected_files,
    })
    if receipt.get("content_sha256") != expected_content:
        _error(result, "RECEIPT_CONTENT_HASH_MISMATCH", "formal receipt content hash does not match")
    if receipt.get("receipt_sha256") != canonical_hash({k: v for k, v in receipt.items() if k != "receipt_sha256"}):
        _error(result, "RECEIPT_SELF_HASH_MISMATCH", "formal receipt self-hash is invalid")

    _validate_reference_files(bundle_root, manifest, sources, result)
    _validate_visual_and_production_approval(approval, result, simulation=bool(receipt.get("simulation")))
    result["ok"] = not result["error_codes"]
    return result


def commit_release(
    bundle_root: Path,
    destination: Path,
    *,
    expected_bundle_id: str = "core-characters-v1.3",
    expected_version: str = "v1.3",
    simulation: bool = False,
) -> dict[str, Any]:
    """Build and atomically switch an isolated release snapshot.

    The source candidate is never modified.  A real caller must provide
    explicit production evidence; test fixtures are accepted only when
    ``simulation=True`` and the evidence itself is marked as a test fixture.
    """
    bundle_root = Path(bundle_root)
    destination = Path(destination)
    result = validate_candidate(
        bundle_root,
        expected_bundle_id=expected_bundle_id,
        expected_version=expected_version,
        simulation=simulation,
    )
    result["mode"] = "commit"
    result["destination"] = str(destination)
    result["mutated_source"] = False
    if not result["ok"]:
        return result
    if bundle_root.resolve() == destination.resolve():
        _error(result, "SOURCE_DESTINATION_COLLISION", "source candidate and release destination must be different")
        result["ok"] = False
        return result
    if destination.exists():
        _error(result, "RELEASE_TARGET_EXISTS", "released version already exists and will not be overwritten")
        result["ok"] = False
        return result

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = Path(tempfile.mkdtemp(prefix=f".{expected_version}-release-", dir=str(destination.parent)))
    staged_snapshot = temp_parent / "bundle"
    try:
        shutil.copytree(bundle_root, staged_snapshot)
        manifest_path = staged_snapshot / "manifest.json"
        approval_path = staged_snapshot / "approval.json"
        manifest = _json(manifest_path)
        approval = _json(approval_path)
        manifest["status"] = "approved-reference"
        manifest["release_status"] = "released"
        manifest["production_enabled"] = True
        for asset in manifest.get("assets", []):
            if isinstance(asset, dict) and asset.get("asset_id") in APPROVED_REFERENCE_IDS:
                asset["approved_for_production"] = True
        approval["release_status"] = "released"
        approval["production_enabled"] = True
        if isinstance(approval.get("formal_production_approval"), dict):
            approval["formal_production_approval"]["release_status"] = "released"
        _write_json(manifest_path, manifest)
        _write_json(approval_path, approval)
        receipt = _formal_receipt(staged_snapshot, manifest, approval, simulation=simulation)
        _write_json(staged_snapshot / "manifest-receipt.json", receipt)
        verified = verify_published_bundle(
            staged_snapshot,
            expected_bundle_id=expected_bundle_id,
            expected_version=expected_version,
        )
        if not verified["ok"]:
            _error(result, "RELEASE_SNAPSHOT_INVALID", "prepared release snapshot failed its own verification")
            result["snapshot_verification"] = verified
            result["ok"] = False
            return result
        if destination.exists():
            _error(result, "RELEASE_TARGET_EXISTS", "release destination appeared during preparation")
            result["ok"] = False
            return result
        os.replace(staged_snapshot, destination)
        result.update(ok=True, receipt_sha256=receipt["receipt_sha256"], simulation=simulation, snapshot_verification=verified)
        return result
    except Exception as exc:
        _error(result, "COMMIT_FAILED", str(exc))
        result["ok"] = False
        return result
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare, verify, or safely commit a character bundle release")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="read-only release preflight")
    prepare_parser.add_argument("--bundle", required=True, type=Path)
    prepare_parser.add_argument("--simulation", action="store_true", help="allow explicitly marked isolated test fixtures")

    commit_parser = subparsers.add_parser("commit", help="commit a validated release snapshot")
    commit_parser.add_argument("--bundle", required=True, type=Path)
    commit_parser.add_argument("--destination", required=True, type=Path)
    commit_parser.add_argument("--simulation", action="store_true", help="allow explicitly marked isolated test fixtures")

    verify_parser = subparsers.add_parser("verify", help="verify a formal release receipt")
    verify_parser.add_argument("--bundle", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare_release(args.bundle, simulation=args.simulation)
    elif args.command == "commit":
        result = commit_release(args.bundle, args.destination, simulation=args.simulation)
    else:
        result = verify_published_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


__all__ = [
    "APPROVED_REFERENCE_IDS",
    "canonical_hash",
    "commit_release",
    "file_hash",
    "main",
    "prepare_release",
    "validate_candidate",
    "verify_published_bundle",
]


if __name__ == "__main__":
    raise SystemExit(main())

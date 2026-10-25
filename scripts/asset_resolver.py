"""Fail-closed resolution for immutable character-bound page assets."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from asset_catalog import validate_page_asset_bindings
from asset_hashing import file_hash, matches_file_hash
from style_lock import (
    APPROVED_REFERENCE_SHA256,
    load_style_master,
    resolve_style_selection,
    validate_registered_style_selection,
    validate_style_master,
)


ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets"
CORE_BUNDLE_ROOT = ASSETS_ROOT / "characters" / "core-v1.2"
CORE_MANIFEST_PATH = CORE_BUNDLE_ROOT / "manifest.json"
ALIASES_PATH = CORE_BUNDLE_ROOT / "aliases.json"
REGISTRY_PATH = ASSETS_ROOT / "page-production-registry.json"
RECEIPT_PATH = CORE_BUNDLE_ROOT / "manifest-receipt.json"
APPROVED_BUNDLE = "core-characters-v1.2"
APPROVED_VERSION = "v1.2"
APPROVED_REFERENCE = "reference/core-character-assets-v1.2.png"
APPROVED_MANIFEST_SHA256 = "cbb4669d776e8fc1fcc2eb47ce798ead237885f599321f7366205dfd0747f30b"
APPROVED_RECEIPT_SHA256 = "e3b22df86aa1989660895c39061690468dd6663955a576a7772001ea7a337659"


def serialize_asset_manifest(manifest: Mapping[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object: {path}")
    return data


def load_core_manifest() -> dict[str, Any]:
    return _load_object(CORE_MANIFEST_PATH)


def load_aliases(path: str | Path = ALIASES_PATH, *, expected_bundle_id: str | None = None) -> dict[str, str]:
    registry = _load_object(Path(path))
    expected = expected_bundle_id or APPROVED_BUNDLE
    if registry.get("bundle_id") != expected:
        raise ValueError("invalid alias registry bundle")
    aliases = registry.get("aliases", {})
    if not isinstance(aliases, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in aliases.items()):
        raise ValueError("invalid alias registry")
    return aliases


def _registry() -> dict[str, Any]:
    return _load_object(REGISTRY_PATH)


def _manifest_receipt(bundle_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(bundle_root).resolve() if bundle_root is not None else CORE_BUNDLE_ROOT.resolve()
    return _load_object(root / "manifest-receipt.json")


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipt_hash(receipt: Mapping[str, Any]) -> str:
    return _canonical_hash({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def _reference_path(manifest: Mapping[str, Any]) -> str | None:
    if not isinstance(manifest, Mapping):
        return None
    visual = manifest.get("visual_reference")
    if not isinstance(visual, Mapping):
        return None
    path = visual.get("path")
    reference_image = visual.get("reference_image")
    if path is not None and reference_image is not None and path != reference_image:
        return None
    value = reference_image if reference_image is not None else path
    return value.strip() if isinstance(value, str) and value.strip() else None


def reference_is_project_safe(manifest: Mapping[str, Any], bundle_root: str | Path | None = None) -> bool:
    reference = _reference_path(manifest)
    if not reference:
        return False
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        return False
    root = Path(bundle_root).resolve() if bundle_root is not None else CORE_BUNDLE_ROOT.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    if not candidate.is_file():
        return False
    expected_hash = APPROVED_REFERENCE_SHA256
    if manifest.get("bundle_id") != APPROVED_BUNDLE or manifest.get("version") != APPROVED_VERSION:
        visual = manifest.get("visual_reference")
        expected_hash = visual.get("reference_sha256") if isinstance(visual, Mapping) else None
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            return False
    try:
        if hashlib.sha256(candidate.read_bytes()).hexdigest().lower() != expected_hash.lower():
            return False
        with Image.open(candidate) as image:
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError):
        return False
    return True


def _character(manifest: Mapping[str, Any], character_id: str) -> Mapping[str, Any] | None:
    return next((item for item in manifest.get("characters", []) if isinstance(item, Mapping) and item.get("character_id") == character_id), None)


def _asset(manifest: Mapping[str, Any], asset_id: Any) -> Mapping[str, Any] | None:
    return next((item for item in manifest.get("assets", []) if isinstance(item, Mapping) and item.get("asset_id") == asset_id), None)


def _valid_asset(asset: Mapping[str, Any], manifest: Mapping[str, Any]) -> bool:
    reference = asset.get("reference_image") or _reference_path(manifest)
    return asset.get("version") == manifest.get("version") and isinstance(reference, str) and bool(reference.strip())


def _asset_reference_path(asset: Mapping[str, Any], manifest: Mapping[str, Any], character_id: str | None = None) -> str | None:
    value = asset.get("reference_image") or _reference_path(manifest)
    if character_id and asset.get("character_id") == "shared":
        character = _character(manifest, character_id)
        if isinstance(character, Mapping):
            value = character.get("reference_image") or value
    return value.strip() if isinstance(value, str) and value.strip() else None


def _asset_reference_hash(asset: Mapping[str, Any], manifest: Mapping[str, Any], bundle_root: str | Path | None, character_id: str | None = None) -> str | None:
    reference = _asset_reference_path(asset, manifest, character_id)
    if not reference:
        return None
    root = Path(bundle_root).resolve() if bundle_root is not None else CORE_BUNDLE_ROOT.resolve()
    candidate = (root / reference).resolve()
    try:
        candidate.relative_to(root)
        if not candidate.is_file():
            return None
        with Image.open(candidate) as image:
            image.verify()
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError):
        return None


def resolve_character_reference_selection(
    manifest: Mapping[str, Any],
    page: Mapping[str, Any],
    aliases: Mapping[str, str] | None = None,
    *,
    bundle_root: str | Path | None = None,
    mode: str = "planning",
) -> list[dict[str, Any]]:
    """Return traceable reference choices without inventing crop metadata."""
    bindings = page.get("characters") if isinstance(page, Mapping) else None
    if not isinstance(bindings, list):
        return []
    reference_file = _reference_path(manifest)
    if not reference_file:
        return []
    style_binding = f"{page.get('style_master_id', 'STYLE-CORE-01')}:{page.get('style_master_version', manifest.get('version', 'v1.2'))}"
    resolved: list[dict[str, Any]] = []
    immutable_aliases = load_aliases()
    alias_map = aliases if aliases is not None else immutable_aliases
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        character = resolve_character_alias(manifest, str(binding.get("character_id", "")), alias_map)
        canonical = character["character_id"]
        character_record = _character(manifest, canonical)
        asset_ids = [character_record.get("identity_asset_id") if character_record else None]
        asset_ids.extend(binding.get(field) for field in ("outfit_id", "expression_id", "pose_id", "angle_id"))
        for asset_id in asset_ids:
            asset = _asset(manifest, asset_id)
            if asset is None or not _valid_asset(asset, manifest):
                continue
            resolved.append({
                "reference_id": f"{canonical}:{asset_id}",
                "character_id": canonical,
                "reference_file": str(_asset_reference_path(asset, manifest, canonical) or reference_file),
                "reference_hash": _asset_reference_hash(asset, manifest, bundle_root, canonical) or APPROVED_REFERENCE_SHA256,
                "reference_purpose": str(asset.get("asset_type", "character-reference")),
                "reference_region": str(asset.get("reference_region", "whole supplied overview")),
                "style_binding": style_binding,
                "validation_status": "approved-reference" if manifest.get("status") == "approved-reference" else "candidate-reference",
            })
    for requested in page.get("character_reference_assets", []) if isinstance(page.get("character_reference_assets"), list) else []:
        if not isinstance(requested, Mapping):
            continue
        asset = _asset(manifest, requested.get("asset_id"))
        if asset is None:
            continue
        reference = _asset_reference_path(asset, manifest)
        if not reference:
            continue
        resolved.append({
            "reference_id": f"aux:{asset.get('asset_id')}",
            "character_id": str(asset.get("character_id") or "shared"),
            "reference_file": reference,
            "reference_hash": _asset_reference_hash(asset, manifest, bundle_root) or "",
            "reference_purpose": str(asset.get("asset_type", "auxiliary-reference")),
            "reference_region": str(asset.get("reference_region", "whole supplied image")),
            "style_binding": style_binding,
            "validation_status": "approved-reference" if manifest.get("status") == "approved-reference" else "candidate-reference",
        })
    return resolved


def resolved_selection_hash(selection: Mapping[str, Any]) -> str:
    locked = {key: value for key, value in selection.items() if key != "resolved_asset_hash"}
    return hashlib.sha256(json.dumps(locked, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def resolve_character_alias(manifest: Mapping[str, Any], character_id: str, aliases: Mapping[str, str] | None = None, *, approved_aliases: Mapping[str, str] | None = None, immutable_aliases: Mapping[str, str] | None = None) -> dict[str, str]:
    immutable_aliases = dict(immutable_aliases or load_aliases())
    if approved_aliases is not None:
        if (not isinstance(approved_aliases, Mapping) or
                not all(isinstance(key, str) and isinstance(value, str) for key, value in approved_aliases.items()) or
                dict(approved_aliases) != immutable_aliases):
            raise ValueError("ALIAS_NOT_APPROVED")
    alias_map = dict(immutable_aliases)
    if aliases is not None:
        if not isinstance(aliases, Mapping):
            raise ValueError("ALIAS_NOT_APPROVED")
        for alias, target in aliases.items():
            if alias not in immutable_aliases or target != immutable_aliases[alias]:
                raise ValueError("ALIAS_NOT_APPROVED")
    canonical = alias_map.get(character_id, character_id)
    character = _character(manifest, canonical)
    if character is None:
        raise ValueError("MISSING_CHARACTER")
    identity = _asset(manifest, character.get("identity_asset_id"))
    if character.get("version") != manifest.get("version") or identity is None or not _valid_asset(identity, manifest) or identity.get("asset_type") != "identity":
        raise ValueError("MISSING_ASSET")
    compatible = identity.get("compatible_characters", [identity.get("character_id")])
    if canonical not in compatible:
        raise ValueError("INCOMPATIBLE_ASSET")
    return {"character_id": canonical, "identity_asset_id": str(character["identity_asset_id"]), "outfit_id": str(character.get("default_outfit", "")), "bundle_id": str(manifest.get("bundle_id", "")), "version": str(manifest.get("version", "")), "reference_image": str(_reference_path(manifest) or "")}


def _failure(code: str, **detail: Any) -> dict[str, Any]:
    return {"ok": False, "failure": {"failure_code": code, **detail}}


def _manifest_failure(manifest: Mapping[str, Any], bundle_root: str | Path | None, mode: str) -> str | None:
    if not isinstance(manifest, Mapping):
        return "ASSET_MANIFEST_NOT_APPROVED"
    is_approved_v12 = manifest.get("bundle_id") == APPROVED_BUNDLE and manifest.get("version") == APPROVED_VERSION
    if manifest.get("status") != "approved-reference":
        if mode == "production":
            return "ASSET_STATUS_NOT_APPROVED"
        if manifest.get("release_status") != "pending_approval" or manifest.get("production_enabled") is True:
            return "ASSET_STATUS_NOT_APPROVED"
    if not is_approved_v12 and mode == "production":
        if manifest.get("bundle_id") == APPROVED_BUNDLE and manifest.get("version") != APPROVED_VERSION:
            return "ASSET_VERSION_NOT_APPROVED"
        if (manifest.get("status") != "approved-reference" or
                manifest.get("release_status") != "released" or
                manifest.get("production_enabled") is not True):
            return "ASSET_STATUS_NOT_APPROVED"
        try:
            from release_character_bundle import verify_published_bundle

            root = Path(bundle_root).resolve() if bundle_root is not None else None
            if root is None:
                return "ASSET_MANIFEST_NOT_APPROVED"
            release_check = verify_published_bundle(
                root,
                expected_bundle_id=str(manifest.get("bundle_id", "")),
                expected_version=str(manifest.get("version", "")),
            )
        except (ImportError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return "ASSET_MANIFEST_NOT_APPROVED"
        if not release_check.get("ok") or release_check.get("simulation") is True:
            return "ASSET_MANIFEST_NOT_APPROVED"
    if not is_approved_v12 and mode not in {"planning", "fixture", "production"}:
        return "ASSET_VERSION_NOT_APPROVED"
    if not reference_is_project_safe(manifest, bundle_root):
        return "REFERENCE_NOT_FOUND"
    if not isinstance(manifest.get("characters"), list) or not isinstance(manifest.get("assets"), list):
        return "ASSET_MANIFEST_NOT_APPROVED"
    if mode == "production" and is_approved_v12:
        try:
            root = Path(bundle_root).resolve() if bundle_root is not None else CORE_BUNDLE_ROOT.resolve()
            receipt = _manifest_receipt(root)
        except (OSError, ValueError, json.JSONDecodeError):
            return "ASSET_MANIFEST_NOT_APPROVED"
        if (receipt.get("schema_version") != 1 or receipt.get("bundle_id") != APPROVED_BUNDLE or
                receipt.get("version") != APPROVED_VERSION or receipt.get("immutable") is not True or
                receipt.get("manifest_sha256") != APPROVED_MANIFEST_SHA256 or
                receipt.get("reference_image") != APPROVED_REFERENCE or
                receipt.get("reference_sha256") != APPROVED_REFERENCE_SHA256 or
                receipt.get("receipt_sha256") != APPROVED_RECEIPT_SHA256 or
                _receipt_hash(receipt) != APPROVED_RECEIPT_SHA256):
            return "ASSET_MANIFEST_NOT_APPROVED"
        files = receipt.get("files")
        if not isinstance(files, Mapping):
            return "ASSET_MANIFEST_NOT_APPROVED"
        expected_files = set(files)
        actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() != "manifest-receipt.json"}
        if actual_files != expected_files:
            return "ASSET_MANIFEST_NOT_APPROVED"
        for relative, digest in files.items():
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts or not isinstance(digest, str):
                return "ASSET_MANIFEST_NOT_APPROVED"
            candidate = (root / relative_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                return "ASSET_MANIFEST_NOT_APPROVED"
            try:
                actual_digest = file_hash(candidate)
            except OSError:
                return "ASSET_MANIFEST_NOT_APPROVED"
            if not candidate.is_file() or not matches_file_hash(candidate, digest):
                return "ASSET_MANIFEST_NOT_APPROVED"
        manifest_path = root / "manifest.json"
        try:
            on_disk_manifest = _load_object(manifest_path)
            manifest_bytes_hash = file_hash(manifest_path)
            selected_manifest_hash = _canonical_hash(manifest)
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            return "ASSET_MANIFEST_NOT_APPROVED"
        if (not matches_file_hash(manifest_path, receipt.get("manifest_bytes_sha256", "")) or
                _canonical_hash(on_disk_manifest) != receipt.get("manifest_sha256") or
                selected_manifest_hash != receipt.get("manifest_sha256")):
            return "ASSET_MANIFEST_NOT_APPROVED"
    return None


def _validate_optional_asset(manifest: Mapping[str, Any], page: Mapping[str, Any], field: str, prefix: str, character_ids: list[str]) -> tuple[str | None, str | None]:
    asset_id = page.get(field)
    if asset_id is None:
        return None, None
    if not isinstance(asset_id, str) or not asset_id.strip():
        return "MISSING_ASSET", None
    asset = _asset(manifest, asset_id)
    if asset is None or not _valid_asset(asset, manifest):
        return "MISSING_ASSET", None
    compatible = asset.get("compatible_characters", [])
    requirement = _registry().get("interaction_requirements", {}).get(prefix, {})
    required = set(requirement.get("required_character_ids", []))
    any_required = set(requirement.get("required_any_character_ids", []))
    cardinality = requirement.get("cardinality", {})
    count = len(character_ids)
    if (asset.get("asset_type") != "interaction" or not asset_id.startswith(prefix) or
            not all(character_id in compatible for character_id in character_ids) or
            not required.issubset(character_ids) or
            (any_required and not any(character_id in any_required for character_id in character_ids)) or
            ("min" in cardinality and count < cardinality["min"]) or
            ("max" in cardinality and count > cardinality["max"])):
        return "INCOMPATIBLE_ASSET", None
    return None, asset_id


def _validate_reference_assets(manifest: Mapping[str, Any], page: Mapping[str, Any], character_ids: list[str], *, mode: str, bundle_root: str | Path | None = None) -> str | None:
    requested = page.get("character_reference_assets")
    if requested is None:
        return None
    if not isinstance(requested, list):
        return "REFERENCE_ASSETS_INVALID"
    seen: set[str] = set()
    for entry in requested:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("asset_id"), str):
            return "REFERENCE_ASSET_INVALID"
        asset_id = entry["asset_id"]
        if asset_id in seen:
            return "REFERENCE_ASSET_INVALID"
        seen.add(asset_id)
        asset = _asset(manifest, asset_id)
        if asset is None or not _valid_asset(asset, manifest) or not _asset_reference_path(asset, manifest):
            return "MISSING_ASSET"
        if asset.get("asset_type") not in {"action-reference", "group-reference"}:
            return "INCOMPATIBLE_ASSET"
        compatible = set(asset.get("compatible_characters", []))
        asset_character_id = asset.get("character_id")
        if asset_character_id and asset_character_id != "shared":
            if asset_character_id not in character_ids or asset_character_id not in compatible:
                return "INCOMPATIBLE_ASSET"
        elif not set(character_ids).issubset(compatible):
            return "INCOMPATIBLE_ASSET"
        if _asset_reference_hash(asset, manifest, bundle_root) is None:
            return "REFERENCE_NOT_FOUND"
        if mode == "production" and asset.get("approved_for_production") is not True:
            return "ASSET_NOT_APPROVED"
    return None


def resolve_page_assets(manifest: Mapping[str, Any], page: Mapping[str, Any], aliases: Mapping[str, str] | None = None, *, bundle_root: str | Path | None = None, style_master: Mapping[str, Any] | None = None, style_bundle_root: str | Path | None = None, mode: str = "production") -> dict[str, Any]:
    """Resolve strict page bindings without accepting unregistered assets."""
    if not isinstance(manifest, Mapping):
        return _failure("ASSET_MANIFEST_NOT_APPROVED")
    if not isinstance(page, Mapping):
        return _failure("INVALID_PAGE_SPEC")
    if mode not in ("production", "fixture", "planning"):
        return _failure("INVALID_MODE")
    if mode == "production":
        from page_production import validate_page_spec

        page_errors = validate_page_spec(page, mode="production" if mode == "production" else mode)
        if page_errors:
            if page_errors and all(error == "characters" for error in page_errors):
                return _failure("EMPTY_CHARACTERS")
            return _failure("INVALID_PAGE_SPEC", detail=", ".join(page_errors))
    binding_errors = validate_page_asset_bindings(page, mode="production" if mode == "production" else "planning")
    if binding_errors:
        return _failure(binding_errors[0])
    problem = _manifest_failure(manifest, bundle_root, mode)
    if problem:
        return _failure(problem)
    requested_style_id = str(page.get("style_master_id", ""))
    if requested_style_id in {"STYLE-CORE-01", "STYLE-01"}:
        try:
            style = load_style_master(reference_root=bundle_root) if style_master is None else style_master
            style_errors = validate_style_master(style, reference_root=bundle_root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _failure("INVALID_STYLE_MASTER", detail=str(exc))
        if style_errors:
            return _failure("INVALID_STYLE_MASTER", detail=", ".join(style_errors))
        try:
            style_selection = resolve_style_selection(
                page.get("style_master_id"),
                mode="production" if mode == "production" else "planning",
                style_master=style,
            )
        except ValueError as exc:
            return _failure("INVALID_STYLE_MASTER", detail=str(exc))
    else:
        try:
            style_selection = resolve_style_selection(
                page.get("style_master_id"),
                mode="production" if mode == "production" else "planning",
                style_master=style_master,
            )
        except ValueError as exc:
            return _failure(str(exc))
        style = style_selection
        canonical_style_id = style_selection["canonical_id"]
        style_errors = validate_registered_style_selection(
            style,
            expected_style_id=canonical_style_id,
            expected_version=str(page.get("style_master_version", "")),
            expected_content_hash=page.get("style_master_content_hash"),
            character_bundle=str(manifest.get("bundle_id", "")),
            profile=str(page.get("profile", "")),
            style_bundle_root=style_bundle_root,
        )
        if style_errors:
            return _failure("INVALID_STYLE_MASTER", detail=", ".join(style_errors))
    if page.get("character_asset_bundle") != manifest.get("bundle_id"):
        return _failure("ASSET_BUNDLE_NOT_APPROVED")
    if page.get("character_asset_version") != manifest.get("version"):
        return _failure("ASSET_VERSION_NOT_APPROVED")
    try:
        alias_path = (Path(bundle_root).resolve() / "aliases.json") if bundle_root is not None else ALIASES_PATH
        approved_aliases = load_aliases(alias_path, expected_bundle_id=str(manifest.get("bundle_id", APPROVED_BUNDLE)))
    except (OSError, ValueError, json.JSONDecodeError):
        return _failure("ALIAS_NOT_APPROVED")
    bindings = page.get("characters")
    if not isinstance(bindings, list) or not bindings:
        return _failure("EMPTY_CHARACTERS")
    selected: list[dict[str, str]] = []
    resolved_character_ids: list[str] = []
    for binding in bindings:
        if not isinstance(binding, Mapping):
            return _failure("MISSING_ASSET")
        try:
            character = resolve_character_alias(manifest, str(binding.get("character_id", "")), aliases, approved_aliases=approved_aliases, immutable_aliases=approved_aliases)
        except ValueError as exc:
            return _failure(str(exc))
        canonical = character["character_id"]
        resolved_character_ids.append(canonical)
        identity_asset = _asset(manifest, character["identity_asset_id"])
        if identity_asset is None or _asset_reference_hash(identity_asset, manifest, bundle_root, canonical) is None:
            return _failure("REFERENCE_NOT_FOUND", asset_id=character["identity_asset_id"])
        resolved = {"character_id": canonical, "identity_asset_id": character["identity_asset_id"]}
        for field, expected_type in (("outfit_id", "outfit"), ("expression_id", "expression"), ("pose_id", "pose"), ("angle_id", "angle")):
            asset_id = binding.get(field)
            asset = _asset(manifest, asset_id)
            if asset is None or not _valid_asset(asset, manifest):
                return _failure("MISSING_ASSET", asset_id=asset_id)
            compatible = asset.get("compatible_characters", [asset.get("character_id")])
            if asset.get("asset_type") != expected_type or canonical not in compatible:
                return _failure("INCOMPATIBLE_ASSET", asset_id=asset_id, character_id=canonical)
            if _asset_reference_hash(asset, manifest, bundle_root, canonical) is None:
                return _failure("REFERENCE_NOT_FOUND", asset_id=asset_id)
            resolved[field] = str(asset_id)
        selected.append(resolved)
    canonical_style_id = style_selection["canonical_id"]
    style_asset = _asset(manifest, canonical_style_id)
    if style_asset is None:
        if canonical_style_id == "STYLE-CORE-01":
            return _failure("MISSING_ASSET", asset_id=canonical_style_id)
    elif (
        not _valid_asset(style_asset, manifest)
        or style_asset.get("asset_type") != "style"
        or page.get("style_master_version") != style.get("version")
        or style_asset.get("style_master_version", style_asset.get("version")) != style.get("version")
        or style.get("style_master_id", style.get("canonical_id")) != canonical_style_id
    ):
        return _failure("INCOMPATIBLE_ASSET", asset_id=canonical_style_id)
    for field, prefix in (("interaction_id", "DUO-"), ("family_interaction_id", "PARENT-")):
        code, _ = _validate_optional_asset(manifest, page, field, prefix, resolved_character_ids)
        if code:
            return _failure(code, asset_id=page.get(field))
    shot_id = page.get("shot_id")
    if shot_id is not None and (not isinstance(shot_id, str) or shot_id not in _registry().get("shot_ids", [])):
        return _failure("MISSING_SHOT", shot_id=shot_id)
    reference_asset_error = _validate_reference_assets(manifest, page, resolved_character_ids, mode=mode, bundle_root=bundle_root)
    if reference_asset_error:
        return _failure(reference_asset_error)
    manifest_content_hash = _canonical_hash(manifest)
    selection = {"bundle_id": manifest["bundle_id"], "version": manifest["version"], "manifest_content_hash": manifest_content_hash, "reference_image": _reference_path(manifest), "characters": selected, "style_master_id": canonical_style_id, "style_master_version": page["style_master_version"], "style_master_content_hash": style["content_hash"], **{field: page[field] for field in ("interaction_id", "family_interaction_id") if field in page}}
    if shot_id is not None:
        selection["shot_id"] = shot_id
    selection["reference_selection"] = resolve_character_reference_selection(manifest, page, aliases, bundle_root=bundle_root, mode=mode)
    selection["resolved_asset_hash"] = resolved_selection_hash(selection)
    return {"ok": True, "asset_selection": selection}

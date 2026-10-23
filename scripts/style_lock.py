"""Immutable style-master loading, validation, and dependency helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, UnidentifiedImageError


STYLE_PATH = Path(__file__).resolve().parents[1] / "assets" / "style_master.json"
STYLE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "assets" / "style-registry.json"
STYLE_ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets"
APPROVED_REFERENCE_IMAGE = "characters/core-v1.2/reference/core-character-assets-v1.2.png"
APPROVED_BUNDLE_REFERENCE = "reference/core-character-assets-v1.2.png"
APPROVED_REFERENCE_SHA256 = "fb16e77d104bc8fb328dab096c4bd83c04245c5310a18a4b6efee404e438af07"
APPROVED_STYLE_CONTENT_HASH = "a7acceeacd62b53de21c0fce89603383a5863ec243b26c79d612f62d8ca9bbf9"
REQUIRED_FIELDS = ("style_master_id", "version", "character_asset_bundle", "reference_image", "reference_sha256", "material", "palette", "line", "lighting", "composition", "social_canvas", "prohibitions", "content_hash")


def style_content_hash(style: Mapping[str, Any]) -> str:
    locked = {key: value for key, value in style.items() if key != "content_hash"}
    return hashlib.sha256(json.dumps(locked, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_style_registry(path: str | Path = STYLE_REGISTRY_PATH) -> dict[str, Any]:
    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("STYLE_REGISTRY_INVALID") from exc
    if registry.get("schema_version") != 1 or not isinstance(registry.get("styles"), list):
        raise ValueError("STYLE_REGISTRY_INVALID")
    for record in registry["styles"]:
        if not isinstance(record, Mapping):
            raise ValueError("STYLE_REGISTRY_INVALID")
        required = ("style_id", "canonical_id", "version", "display_name", "status", "aliases", "reference_assets", "compatibility", "description")
        if any(field not in record for field in required) or not isinstance(record.get("aliases"), list) or not isinstance(record.get("reference_assets"), list):
            raise ValueError("STYLE_REGISTRY_INVALID")
    return registry


def resolve_style_selection(style_id: str | None, *, mode: str = "planning", style_master: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if mode not in {"planning", "production"}:
        raise ValueError("INVALID_STYLE_MODE")
    registry = load_style_registry()
    requested = str(style_id or registry.get("default_style_id") or "").strip()
    record = next(
        (
            item for item in registry["styles"]
            if item.get("style_id") == requested
            or item.get("canonical_id") == requested
            or requested in item.get("aliases", [])
        ),
        None,
    )
    if record is None:
        raise ValueError("UNKNOWN_STYLE")
    status = record.get("status")
    if status == "deprecated":
        raise ValueError("STYLE_DEPRECATED")
    if mode == "production" and status != "approved":
        raise ValueError("STYLE_NOT_APPROVED")
    selection = dict(record)
    selection["requested_style_id"] = requested
    selection["canonical_id"] = str(record.get("canonical_id") or record.get("style_id"))
    if selection["canonical_id"] == "STYLE-CORE-01":
        master = load_style_master() if style_master is None else style_master
        compatibility = record.get("compatibility", {})
        if (
            master.get("style_master_id") != selection["canonical_id"]
            or master.get("version") != record.get("version")
            or master.get("content_hash") != record.get("content_hash")
            or compatibility.get("style_master_version") != master.get("version")
        ):
            raise ValueError("STYLE_REGISTRY_MISMATCH")
    return selection


def _style_reference_candidate(root: Path, relative: str) -> Path | None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    candidates = [root / path]
    if path.parts[0] == root.name:
        candidates.insert(0, root.joinpath(*path.parts[1:]))
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def validate_registered_style_selection(
    selection: Mapping[str, Any],
    *,
    expected_style_id: str,
    expected_version: str,
    expected_content_hash: str | None = None,
    character_bundle: str | None = None,
    profile: str | None = None,
    style_bundle_root: str | Path | None = None,
) -> list[str]:
    """Validate an explicitly selected non-default style from the registry.

    The legacy STYLE-CORE-01 path is intentionally handled by
    ``validate_style_master``. This path is for released style bundles such as
    STYLE-06 and never changes the registry's default style.
    """
    errors: list[str] = []
    canonical_id = str(selection.get("canonical_id") or selection.get("style_id") or "")
    if canonical_id != expected_style_id or selection.get("style_id") != expected_style_id:
        errors.append("style_master_id")
    if selection.get("version") != expected_version:
        errors.append("version")
    if selection.get("status") != "approved":
        errors.append("status")
    declared_hash = selection.get("content_hash")
    registry_payload = {
        key: value
        for key, value in selection.items()
        if key not in {"content_hash", "requested_style_id"}
    }
    registry_hash = hashlib.sha256(
        json.dumps(registry_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not isinstance(declared_hash, str) or declared_hash != registry_hash:
        errors.append("content_hash")
    if expected_content_hash and declared_hash != expected_content_hash:
        errors.append("declared_content_hash")
    compatibility = selection.get("compatibility")
    if not isinstance(compatibility, Mapping):
        errors.append("compatibility")
    else:
        if character_bundle and compatibility.get("character_asset_bundle") != character_bundle:
            errors.append("character_asset_bundle")
        if profile and compatibility.get("profile") != profile:
            errors.append("profile")

    references = selection.get("reference_assets")
    if not isinstance(references, list) or not references:
        errors.append("reference_assets")
        references = []
    root = Path(style_bundle_root).resolve() if style_bundle_root else STYLE_ASSETS_ROOT.resolve()
    selected_reference_hashes: set[str] = set()
    for reference in references:
        if not isinstance(reference, Mapping):
            errors.append("reference_assets")
            continue
        if reference.get("validation_status") != "approved-reference":
            errors.append("reference_status")
        expected_reference_hash = reference.get("reference_hash")
        relative = reference.get("reference_file")
        if not isinstance(relative, str) or not isinstance(expected_reference_hash, str):
            errors.append("reference_metadata")
            continue
        candidate = _style_reference_candidate(root, relative)
        if candidate is None:
            errors.append("reference_image")
            continue
        if _sha256(candidate) != expected_reference_hash.lower():
            errors.append("reference_sha256")
        selected_reference_hashes.add(expected_reference_hash.lower())

    if style_bundle_root:
        bundle = Path(style_bundle_root).resolve()
        try:
            bundle_manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            approval = json.loads((bundle / "approval.json").read_text(encoding="utf-8"))
            receipt = json.loads((bundle / "manifest-receipt.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("style_bundle")
        else:
            visual = bundle_manifest.get("visual_reference", {})
            bundle_reference = _style_reference_candidate(bundle, str(visual.get("reference_image", "")))
            if (
                bundle_manifest.get("style_id") != expected_style_id
                or bundle_manifest.get("version") != expected_version
                or bundle_manifest.get("status") != "approved"
                or bundle_manifest.get("production_approval", {}).get("status") != "approved"
                or approval.get("formal_production_approval_status") != "approved"
                or approval.get("production_enabled_for_explicit_selection") is not True
                or bundle_reference is None
                or _sha256(bundle_reference) not in selected_reference_hashes
            ):
                errors.append("style_bundle_approval")
            files = receipt.get("files", {})
            expected_receipt_hash = receipt.get("receipt_sha256")
            actual_receipt_hash = hashlib.sha256(
                json.dumps(
                    {key: value for key, value in receipt.items() if key != "receipt_sha256"},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if (
                receipt.get("style_id") != expected_style_id
                or receipt.get("version") != expected_version
                or receipt.get("integrity_verified") is not True
                or not isinstance(files, Mapping)
                or any(
                    not isinstance(relative_path, str)
                    or not (bundle / relative_path).is_file()
                    or _sha256(bundle / relative_path) != expected_hash
                    for relative_path, expected_hash in files.items()
                )
                or expected_receipt_hash != actual_receipt_hash
            ):
                errors.append("style_bundle_receipt")
    return sorted(set(errors))


def validate_style_master(style: Mapping[str, Any], *, assets_root: str | Path | None = None, reference_root: str | Path | None = None) -> list[str]:
    if not isinstance(style, Mapping):
        return ["style_master: expected an object"]
    errors = [field for field in REQUIRED_FIELDS if not style.get(field)]
    if style.get("immutable") is not True:
        errors.append("immutable")
    if style.get("version") != "v1.2":
        errors.append("version")
    if style.get("character_asset_bundle") != "core-characters-v1.2":
        errors.append("character_asset_bundle")
    social_canvas = style.get("social_canvas")
    if not isinstance(social_canvas, Mapping) or social_canvas.get("profile") != "xiaohongshu-feed-3x4" or social_canvas.get("aspect_ratio") != "3:4" or social_canvas.get("native_width_px") != 1080 or social_canvas.get("native_height_px") != 1440:
        errors.append("social_canvas")
    relative = style.get("reference_image")
    if relative != APPROVED_REFERENCE_IMAGE:
        errors.append("reference_image")
    else:
        root = Path(reference_root).resolve() if reference_root else (Path(assets_root).resolve() if assets_root else STYLE_PATH.parent)
        candidate = (root / (APPROVED_BUNDLE_REFERENCE if reference_root else relative)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append("reference_image")
        else:
            if not candidate.is_file():
                errors.append("reference_image")
            elif not isinstance(style.get("reference_sha256"), str) or style["reference_sha256"].lower() != APPROVED_REFERENCE_SHA256:
                errors.append("reference_sha256")
            else:
                try:
                    with Image.open(candidate) as image:
                        image.verify()
                except (OSError, SyntaxError, ValueError, UnidentifiedImageError):
                    errors.append("reference_image")
                try:
                    actual_reference_hash = hashlib.sha256(candidate.read_bytes()).hexdigest().lower()
                except OSError:
                    actual_reference_hash = ""
                if actual_reference_hash != APPROVED_REFERENCE_SHA256:
                    errors.append("reference_sha256")
    if style.get("content_hash") != style_content_hash(style) or style.get("content_hash") != APPROVED_STYLE_CONTENT_HASH:
        errors.append("content_hash")
    return errors


def load_style_master(path: str | Path = STYLE_PATH, *, reference_root: str | Path | None = None) -> dict[str, Any]:
    style = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_style_master(style, assets_root=Path(path).resolve().parent, reference_root=reference_root)
    if errors:
        raise ValueError("INVALID_STYLE_MASTER: " + ", ".join(errors))
    return style


def affected_pages_for_style_change(pages: Sequence[Mapping[str, Any]], old_style_id: str, new_style_id: str) -> list[str]:
    if old_style_id == new_style_id:
        return []
    return [page["page_id"] for page in pages if page.get("style_master_id") == old_style_id]

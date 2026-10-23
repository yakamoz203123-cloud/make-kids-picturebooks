"""Small, metadata-only catalog for Phase 1 scene and prop bindings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets"
SCENE_REGISTRY_PATH = ASSETS_ROOT / "scene-registry.json"
PROP_REGISTRY_PATH = ASSETS_ROOT / "prop-registry.json"
APPROVED_STATUS = "approved"
PLANNING_STATUSES = {"candidate", "registered-unverified", APPROVED_STATUS}


def _load_object(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"ASSET_REGISTRY_INVALID: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"ASSET_REGISTRY_INVALID: {path}")
    return value


def _load_registry(path: str | Path, item_key: str) -> dict[str, Any]:
    value = _load_object(path)
    if value.get("schema_version") != 1 or not isinstance(value.get(item_key), list):
        raise ValueError(f"ASSET_REGISTRY_INVALID: {path}")
    return value


def load_scene_registry(path: str | Path = SCENE_REGISTRY_PATH) -> dict[str, Any]:
    return _load_registry(path, "scenes")


def load_prop_registry(path: str | Path = PROP_REGISTRY_PATH) -> dict[str, Any]:
    return _load_registry(path, "props")


def _record(registry: Mapping[str, Any], key: str, identifier: str) -> Mapping[str, Any] | None:
    return next((item for item in registry.get(key, []) if isinstance(item, Mapping) and item.get("scene_id", item.get("prop_id")) == identifier), None)


def _mode_check(status: str, mode: str, *, scene: bool) -> None:
    if mode not in {"planning", "production"}:
        raise ValueError("INVALID_ASSET_MODE")
    if status == "deprecated":
        raise ValueError("SCENE_DEPRECATED" if scene else "PROP_DEPRECATED")
    if mode == "production" and status != APPROVED_STATUS:
        raise ValueError("SCENE_NOT_APPROVED" if scene else "PROP_NOT_APPROVED")
    if mode == "planning" and status not in PLANNING_STATUSES:
        raise ValueError("SCENE_STATUS_INVALID" if scene else "PROP_STATUS_INVALID")


def _reference(value: Any, id_key: str, *, scene: bool) -> tuple[str, str | None, str | None]:
    if isinstance(value, str) and value.strip():
        return value.strip(), None, None
    if not isinstance(value, Mapping):
        raise ValueError("MISSING_SCENE" if scene else "MISSING_PROP")
    identifier = value.get(id_key) or value.get("asset_id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("MISSING_SCENE" if scene else "MISSING_PROP")
    version = value.get("version")
    state_id = value.get("state_id")
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise ValueError("SCENE_VERSION_INVALID" if scene else "PROP_VERSION_INVALID")
    if state_id is not None and (not isinstance(state_id, str) or not state_id.strip()):
        raise ValueError("SCENE_STATE_INVALID" if scene else "INVALID_PROP_STATE")
    return identifier.strip(), version, state_id


def resolve_scene_ref(value: Any, *, mode: str = "production") -> dict[str, Any]:
    identifier, version, state_id = _reference(value, "scene_id", scene=True)
    record = _record(load_scene_registry(), "scenes", identifier)
    if record is None:
        raise ValueError("MISSING_SCENE")
    if version is not None and version != record.get("version"):
        raise ValueError("SCENE_VERSION_NOT_APPROVED")
    _mode_check(str(record.get("status", "")), mode, scene=True)
    resolved = dict(record)
    resolved["requested_scene_id"] = identifier
    if state_id is not None:
        resolved["state_id"] = state_id
    return resolved


def resolve_prop_ref(value: Any, *, mode: str = "production") -> dict[str, Any]:
    identifier, version, state_id = _reference(value, "prop_id", scene=False)
    record = _record(load_prop_registry(), "props", identifier)
    if record is None:
        raise ValueError("MISSING_PROP")
    if version is not None and version != record.get("version"):
        raise ValueError("PROP_VERSION_NOT_APPROVED")
    allowed_states = record.get("allowed_states")
    if state_id is None:
        raise ValueError("MISSING_PROP_STATE")
    if not isinstance(allowed_states, list) or state_id not in allowed_states:
        raise ValueError("INVALID_PROP_STATE")
    _mode_check(str(record.get("status", "")), mode, scene=False)
    resolved = dict(record)
    resolved["requested_prop_id"] = identifier
    resolved["state_id"] = state_id
    return resolved


def validate_page_asset_bindings(page: Mapping[str, Any], *, mode: str = "production") -> list[str]:
    """Validate only optional Phase 1 bindings; legacy text props remain valid."""
    if not isinstance(page, Mapping):
        return ["INVALID_PAGE_SPEC"]
    errors: list[str] = []
    if "scene_ref" in page and page.get("scene_ref") is not None:
        try:
            resolve_scene_ref(page["scene_ref"], mode=mode)
        except ValueError as exc:
            errors.append(str(exc))
    props = page.get("props")
    if isinstance(props, list):
        for prop in props:
            if not isinstance(prop, Mapping):
                continue
            if "asset_id" in prop or "prop_id" in prop:
                try:
                    resolve_prop_ref(prop, mode=mode)
                except ValueError as exc:
                    errors.append(str(exc))
    asset_refs = page.get("asset_refs")
    if asset_refs is not None:
        if not isinstance(asset_refs, list):
            errors.append("ASSET_REFS_INVALID")
        else:
            for ref in asset_refs:
                if not isinstance(ref, Mapping):
                    errors.append("ASSET_REF_INVALID")
                    continue
                asset_type = ref.get("asset_type") or ref.get("type")
                try:
                    if asset_type == "scene":
                        resolve_scene_ref(ref, mode=mode)
                    elif asset_type == "prop":
                        resolve_prop_ref(ref, mode=mode)
                    else:
                        errors.append("ASSET_REF_TYPE_INVALID")
                except ValueError as exc:
                    errors.append(str(exc))
    return errors

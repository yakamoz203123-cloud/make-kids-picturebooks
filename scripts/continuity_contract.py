"""Optional, deterministic continuity constraints for picturebook page tasks.

This module validates declared contracts and assembles reminders for the host
task.  It does not inspect pixels and it never approves a visual result.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CONTINUITY_SCHEMA_VERSION = 1
_REFERENCE_RELATIONS = {"previous", "next", "key", "comparison"}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _block(code: str, message: str, *, field: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message, "severity": "block"}
    if field:
        result["field"] = field
    return result


def _warning(code: str, message: str, *, field: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message, "severity": "warn"}
    if field:
        result["field"] = field
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_project_path(project_root: Path, value: str) -> Path | None:
    try:
        candidate = (project_root / Path(value)).resolve()
        candidate.relative_to(project_root)
    except (OSError, ValueError):
        return None
    return candidate


def _page_id(page: Mapping[str, Any]) -> str:
    number = page.get("page")
    return str(page.get("page_id") or (f"PAGE-{int(number):02d}" if isinstance(number, int) else "unknown-page"))


def _validate_character(value: Any, index: int, blocks: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any] | None:
    field = f"character[{index}]"
    if not isinstance(value, Mapping):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "character entry must be an object", field=field))
        return None
    if not _nonempty(value.get("character_id")):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "character_id is required", field=f"{field}.character_id"))
    fixed = value.get("fixed")
    if fixed is not None and not isinstance(fixed, Mapping):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "fixed must be an object", field=f"{field}.fixed"))
    for key in ("required_action", "before_state", "current_state", "after_state"):
        if key in value and value[key] is not None and not _nonempty(value[key]):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", f"{key} must be a nonempty string", field=f"{field}.{key}"))
    if fixed is None:
        warnings.append(_warning("CONTINUITY_CHARACTER_FIXED_UNDECLARED", "character fixed appearance is not fully declared", field=field))
    return copy.deepcopy(dict(value))


def _validate_prop(value: Any, index: int, blocks: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any] | None:
    field = f"recurring_props[{index}]"
    if not isinstance(value, Mapping):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "recurring prop entry must be an object", field=field))
        return None
    if not _nonempty(value.get("prop_id")):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "prop_id is required", field=f"{field}.prop_id"))
    definition = value.get("definition")
    if not isinstance(definition, Mapping):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "definition must be an object", field=f"{field}.definition"))
    else:
        for key in ("shape", "material", "ratio"):
            if key in definition and not _nonempty(definition[key]) and not isinstance(definition[key], (int, float)):
                blocks.append(_block("CONTINUITY_SCHEMA_INVALID", f"definition.{key} must be nonempty", field=f"{field}.definition.{key}"))
    pages = value.get("pages")
    if not isinstance(pages, list) or not pages or any(type(item) is not int or item < 1 for item in pages):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "pages must be a nonempty list of positive integers", field=f"{field}.pages"))
    allowed = value.get("allowed_changes")
    if not isinstance(allowed, list) or any(not _nonempty(item) for item in allowed):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "allowed_changes must be a list of strings", field=f"{field}.allowed_changes"))
    if isinstance(allowed, list) and not allowed:
        warnings.append(_warning("CONTINUITY_PROP_NO_ALLOWED_VARIATION", "prop has no declared allowed variation", field=field))
    return copy.deepcopy(dict(value))


def _validate_scene(value: Any, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    field = "scene_and_lighting"
    if not isinstance(value, Mapping):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "scene_and_lighting must be an object", field=field))
        return None
    for key in ("scene_id", "light_direction", "shadow_direction"):
        if key in value and not _nonempty(value[key]):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", f"{key} must be a nonempty string", field=f"{field}.{key}"))
    if "shadow_foot_connection" in value and type(value["shadow_foot_connection"]) is not bool:
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "shadow_foot_connection must be boolean", field=f"{field}.shadow_foot_connection"))
    if "shadow_rules" in value:
        if not isinstance(value["shadow_rules"], list) or any(not _nonempty(item) for item in value["shadow_rules"]):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "shadow_rules must be a list of strings", field=f"{field}.shadow_rules"))
    return copy.deepcopy(dict(value))


def _validate_science(value: Any, blocks: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, Any] | list[dict[str, Any]] | None:
    field = "science_stages"
    if isinstance(value, list):
        result = []
        for index, stage in enumerate(value):
            if not isinstance(stage, Mapping):
                blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "science stage entry must be an object", field=f"{field}[{index}]"))
                continue
            if not _nonempty(stage.get("stage_id")):
                blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "stage_id is required", field=f"{field}[{index}].stage_id"))
            order = stage.get("stage_order", stage.get("order"))
            if type(order) is not int or order < 1:
                blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "stage_order must be a positive integer", field=f"{field}[{index}].stage_order"))
            result.append(copy.deepcopy(dict(stage)))
        return result
    if not isinstance(value, Mapping):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "science_stages must be an object or list", field=field))
        return None
    current = value.get("current_stage_id", value.get("stage_id"))
    if current is not None and not _nonempty(current):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "current_stage_id must be nonempty", field=f"{field}.current_stage_id"))
    order = value.get("stage_order", value.get("order"))
    if order is not None and (type(order) is not int or order < 1):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "stage_order must be a positive integer", field=f"{field}.stage_order"))
    if current is None:
        warnings.append(_warning("CONTINUITY_SCIENCE_STAGE_NOT_EXPLICIT", "science stage is recorded without a current stage id", field=field))
    return copy.deepcopy(dict(value))


def _validate_references(
    value: Any,
    *,
    project_root: Path | None,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    field = "reference_pages"
    if not isinstance(value, list):
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "reference_pages must be a list", field=field))
        return None
    result: list[dict[str, Any]] = []
    for index, reference in enumerate(value):
        ref_field = f"{field}[{index}]"
        if not isinstance(reference, Mapping):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "reference must be an object", field=ref_field))
            continue
        if type(reference.get("page")) is not int or reference["page"] < 1:
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "reference page must be a positive integer", field=f"{ref_field}.page"))
        if reference.get("relation") not in _REFERENCE_RELATIONS:
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "unsupported reference relation", field=f"{ref_field}.relation"))
        path_value = reference.get("path")
        expected_hash = reference.get("sha256")
        if not _nonempty(path_value):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "reference path is required", field=f"{ref_field}.path"))
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "reference sha256 must be a 64-character string", field=f"{ref_field}.sha256"))
        normalized = copy.deepcopy(dict(reference))
        if project_root is not None and _nonempty(path_value):
            candidate = _safe_project_path(project_root, path_value)
            if candidate is None:
                blocks.append(_block("CONTINUITY_REFERENCE_PATH_ESCAPE", "reference path must stay inside the project", field=f"{ref_field}.path"))
            elif not candidate.is_file():
                blocks.append(_block("CONTINUITY_REFERENCE_NOT_FOUND", "declared reference file does not exist", field=f"{ref_field}.path"))
            elif isinstance(expected_hash, str) and len(expected_hash) == 64 and _sha256(candidate).lower() != expected_hash.lower():
                blocks.append(_block("CONTINUITY_REFERENCE_HASH_MISMATCH", "declared reference SHA-256 does not match the file", field=f"{ref_field}.sha256"))
            if candidate is not None:
                normalized["resolved_path"] = candidate.as_posix()
        result.append(normalized)
    return result


def _stage_ids(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        current = value.get("current_stage_id", value.get("stage_id"))
        return [current] if _nonempty(current) else []
    if isinstance(value, list):
        return [item["stage_id"] for item in value if isinstance(item, Mapping) and _nonempty(item.get("stage_id"))]
    return []


def _prompt_addendum(binding: Mapping[str, Any], warnings: list[dict[str, Any]]) -> str:
    lines = ["CONTINUITY INVARIANTS — metadata reminders; final visual review remains required."]
    for character in binding.get("character", []):
        action = character.get("required_action") or "preserve declared character state"
        fixed = character.get("fixed") or {}
        lines.append(f"character {character.get('character_id')}: {action}; fixed={json.dumps(fixed, ensure_ascii=False, sort_keys=True)}")
    for prop in binding.get("recurring_props", []):
        definition = prop.get("definition") or {}
        lines.append(f"prop {prop.get('prop_id')}: {json.dumps(definition, ensure_ascii=False, sort_keys=True)}; pages={prop.get('pages')}")
    scene = binding.get("scene_and_lighting")
    if scene:
        lines.append(f"scene/light: {json.dumps(scene, ensure_ascii=False, sort_keys=True)}")
    science = binding.get("science_stages")
    if science:
        lines.append(f"science stage: {json.dumps(science, ensure_ascii=False, sort_keys=True)}")
    for reference in binding.get("reference_pages", []):
        lines.append(f"reference page {reference.get('page')} ({reference.get('relation')}): {reference.get('path')} sha256={reference.get('sha256')}")
    if warnings:
        lines.append("visual reminders: " + "; ".join(item["message"] for item in warnings))
    return "\n".join(lines)


def validate_continuity_invariants(
    page: Mapping[str, Any],
    *,
    project_root: str | Path | None = None,
    storyboard_page: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the optional contract and return blocks/warnings/binding.

    A missing contract is intentionally a no-op for legacy manifests.  A
    declared contract is strict about structure and reference integrity, but
    it does not infer visual truth from metadata.
    """
    blocks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    raw = page.get("continuity_invariants") if isinstance(page, Mapping) else None
    if raw is None:
        return {
            "schema_version": CONTINUITY_SCHEMA_VERSION,
            "status": "not_applicable",
            "page_id": _page_id(page),
            "binding": None,
            "blocks": [],
            "warnings": [],
            "prompt_addendum": "",
        }
    if not isinstance(raw, Mapping):
        return {
            "schema_version": CONTINUITY_SCHEMA_VERSION,
            "status": "blocked",
            "page_id": _page_id(page),
            "binding": None,
            "blocks": [_block("CONTINUITY_SCHEMA_INVALID", "continuity_invariants must be an object", field="continuity_invariants")],
            "warnings": [],
            "prompt_addendum": "",
        }
    if raw.get("schema_version", CONTINUITY_SCHEMA_VERSION) != CONTINUITY_SCHEMA_VERSION:
        blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "unsupported continuity schema version", field="continuity_invariants.schema_version"))

    binding: dict[str, Any] = {"schema_version": CONTINUITY_SCHEMA_VERSION}
    if "character" in raw:
        if not isinstance(raw["character"], list):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "character must be a list", field="continuity_invariants.character"))
        else:
            binding["character"] = [item for index, value in enumerate(raw["character"]) if (item := _validate_character(value, index, blocks, warnings)) is not None]
    if "recurring_props" in raw:
        if not isinstance(raw["recurring_props"], list):
            blocks.append(_block("CONTINUITY_SCHEMA_INVALID", "recurring_props must be a list", field="continuity_invariants.recurring_props"))
        else:
            binding["recurring_props"] = [item for index, value in enumerate(raw["recurring_props"]) if (item := _validate_prop(value, index, blocks, warnings)) is not None]
    if "scene_and_lighting" in raw:
        scene = _validate_scene(raw["scene_and_lighting"], blocks)
        if scene is not None:
            binding["scene_and_lighting"] = scene
    if "science_stages" in raw:
        science = _validate_science(raw["science_stages"], blocks, warnings)
        if science is not None:
            binding["science_stages"] = science
    if "reference_pages" in raw:
        references = _validate_references(
            raw["reference_pages"],
            project_root=Path(project_root).resolve() if project_root is not None else None,
            blocks=blocks,
        )
        if references is not None:
            binding["reference_pages"] = references
    elif any(key in raw for key in ("character", "recurring_props", "scene_and_lighting", "science_stages")):
        warnings.append(_warning("CONTINUITY_REFERENCE_NOT_DECLARED", "no reference page was declared for the continuity contract", field="continuity_invariants.reference_pages"))

    expected_stages = _stage_ids(raw.get("science_stages"))
    explicit_sources = []
    for source_name, source in (("page", page), ("storyboard", storyboard_page)):
        if isinstance(source, Mapping):
            value = source.get("science_stage_id")
            if _nonempty(value):
                explicit_sources.append((source_name, value))
    if expected_stages:
        for source_name, source_stage in explicit_sources:
            if source_stage not in expected_stages:
                blocks.append(_block(
                    "CONTINUITY_SCIENCE_STAGE_CONTRADICTION",
                    f"{source_name} science stage {source_stage!r} conflicts with declared stage {expected_stages!r}",
                    field=f"{source_name}.science_stage_id",
                ))

    binding["page_id"] = _page_id(page)
    binding["page_version"] = page.get("page_version")
    if "character" in binding and not binding["character"]:
        warnings.append(_warning("CONTINUITY_CHARACTER_EMPTY", "no character continuity records were bound", field="continuity_invariants.character"))
    if "scene_and_lighting" in binding and "shadow_direction" not in binding["scene_and_lighting"]:
        warnings.append(_warning("CONTINUITY_LIGHTING_PARTIAL", "shadow direction was not declared", field="continuity_invariants.scene_and_lighting"))
    prompt = _prompt_addendum(binding, warnings)
    return {
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "status": "blocked" if blocks else "passed",
        "page_id": _page_id(page),
        "binding": binding,
        "blocks": blocks,
        "warnings": warnings,
        "prompt_addendum": prompt,
    }


def assemble_continuity_task(
    page: Mapping[str, Any],
    *,
    storyboard_page: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build the continuity part of the existing host page task."""
    result = validate_continuity_invariants(page, project_root=project_root, storyboard_page=storyboard_page)
    if result["blocks"]:
        first = result["blocks"][0]
        raise ValueError(f"{first['code']}: {first['message']}")
    if result["status"] == "not_applicable":
        return {
            "schema_version": CONTINUITY_SCHEMA_VERSION,
            "status": "not_applicable",
            "page_id": result["page_id"],
            "binding": None,
            "prompt_addendum": "",
            "warnings": [],
            "blocks": [],
        }
    return {
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "status": "ready",
        "page_id": result["page_id"],
        "binding": result["binding"],
        "prompt_addendum": result["prompt_addendum"],
        "warnings": result["warnings"],
        "blocks": [],
    }


def build_continuity_review_record(
    page: Mapping[str, Any],
    continuity_task: Mapping[str, Any],
    *,
    discovery_stage: str = "pre_generation",
    human_final_conclusion: str = "pending",
    rework_needed: str = "unknown",
    current_image_path: str | None = None,
    current_image_sha256: str | None = None,
) -> dict[str, Any]:
    """Create review evidence without converting structural checks to approval."""
    binding = copy.deepcopy(continuity_task.get("binding"))
    references = copy.deepcopy((binding or {}).get("reference_pages", [])) if isinstance(binding, Mapping) else []
    questions = [
        "角色身份、服装、发型和动作是否与已发布资产及相邻页一致？",
        "重复道具的形状、比例、材质和数量是否保持可识别连续？",
        "场景、光源和影子方向是否与前后页保持空间关系？",
        "科学阶段的可见部分、未出现部分和故事文字是否相互一致？",
    ]
    return {
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "current_page": {
            "page_id": _page_id(page),
            "page_version": page.get("page_version"),
            "image_path": current_image_path if current_image_path is not None else page.get("current_image_path"),
            "image_sha256": current_image_sha256 if current_image_sha256 is not None else "unknown",
        },
        "constraints": binding,
        "references": references,
        "structural_preflight": {
            "status": "passed" if not continuity_task.get("blocks") else "blocked",
            "warnings": copy.deepcopy(continuity_task.get("warnings", [])),
            "evidence": "metadata and reference-file checks only; visual truth not inferred",
        },
        "human_visual_questions": questions,
        "discovery_stage": discovery_stage,
        "rework_needed": rework_needed,
        "human_final_conclusion": human_final_conclusion,
    }

"""Strict page-production contracts, kept separate from the generation queue.

Production mode is the default and requires the complete asset-bound page record.
The compact binding shape is available only through the explicit test-only
``mode="fixture"`` path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from asset_resolver import load_aliases, load_core_manifest, resolve_page_assets
from continuity_contract import assemble_continuity_task, build_continuity_review_record


REQUIRED_PAGE_FIELDS = ("page_id", "page_version", "story_version", "character_asset_bundle", "character_asset_version", "characters", "style_master_id", "style_master_version", "page_delta")
REQUIRED_CHARACTER_FIELDS = ("character_id", "outfit_id", "expression_id", "pose_id", "angle_id")
FULL_RECORD_FIELDS = ("text", "text_safe_area", "continuity", "source_prompt_hash", "resolved_asset_hash", "current_image_path", "review_status", "shot_id", "profile", "declared_aspect_ratio", "style_master_content_hash")
PRODUCTION_SCHEMA = "asset-bound-page-v1"
VISUAL_DIRECTION_FIELDS = (
    "story_task",
    "visual_subject",
    "must_show",
    "must_not_show",
    "visual_result",
    "science_evidence",
    "composition_reason",
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _visual_direction(
    page: Mapping[str, Any], storyboard_page: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the page's explicit visual contract without changing legacy fields.

    Storyboard data is authoritative when present; the manifest copy remains a
    compatibility fallback for hosts that assemble tasks from page records.
    The payload is descriptive only and never substitutes for visual review.
    """
    for source in (storyboard_page, page):
        if not isinstance(source, Mapping):
            continue
        value = source.get("visual_direction")
        if isinstance(value, Mapping):
            return {key: value[key] for key in value if key in VISUAL_DIRECTION_FIELDS}
    return None


def validate_page_spec(page: Mapping[str, Any], *, mode: str = "production") -> list[str]:
    if not isinstance(page, Mapping):
        return ["page: expected an object"]
    if mode not in ("production", "fixture", "planning"):
        return ["mode: expected production, planning or fixture"]
    errors = [field for field in REQUIRED_PAGE_FIELDS if not page.get(field)]
    if mode == "production":
        if page.get("production_schema") != PRODUCTION_SCHEMA:
            errors.append("production_schema")
        errors.extend(field for field in FULL_RECORD_FIELDS if field not in page or (field != "current_image_path" and not page.get(field)))
        if page.get("profile") != "xiaohongshu-feed-3x4":
            errors.append("profile")
        if page.get("declared_aspect_ratio") != "3:4":
            errors.append("declared_aspect_ratio")
    if page.get("character_asset_version") and page["character_asset_version"] not in {"v1.2", "v1.3"}:
        errors.append("character_asset_version: version is not approved")
    if page.get("style_master_version") is not None and not _nonempty(page.get("style_master_version")):
        errors.append("style_master_version")
    if mode == "fixture" and page.get("style_master_version") not in {None, "v1.2"}:
        errors.append("style_master_version: version is not approved")
    characters = page.get("characters")
    if isinstance(characters, list):
        if not characters:
            errors.append("characters")
        for number, character in enumerate(characters):
            if not isinstance(character, Mapping):
                errors.append(f"characters[{number}]: expected an object")
            else:
                errors.extend(field for field in REQUIRED_CHARACTER_FIELDS if not _nonempty(character.get(field)))
    for field in ("interaction_id", "family_interaction_id"):
        if field in page and page[field] is not None and not _nonempty(page[field]):
            errors.append(field)
    if "shot_id" in page and not _nonempty(page["shot_id"]):
        errors.append("shot_id")
    if "current_image_path" in page and page["current_image_path"] is not None and not _nonempty(page["current_image_path"]):
        errors.append("current_image_path")
    return errors


def build_page_prompt(page: Mapping[str, Any], aliases: Mapping[str, str] | None = None, *, manifest: Mapping[str, Any] | None = None, bundle_root: str | Path | None = None, style_master: Mapping[str, Any] | None = None, style_bundle_root: str | Path | None = None, mode: str = "production") -> dict[str, Any]:
    errors = validate_page_spec(page, mode=mode)
    if errors:
        raise ValueError("INVALID_PAGE_SPEC: " + ", ".join(errors))
    if manifest is None and page.get("character_asset_version") not in {None, "", "v1.2"}:
        raise ValueError("ASSET_MANIFEST_REQUIRED_FOR_SELECTED_VERSION")
    selected_manifest = load_core_manifest() if manifest is None else manifest
    result = resolve_page_assets(selected_manifest, page, aliases if aliases is not None else load_aliases(), bundle_root=bundle_root, style_master=style_master, style_bundle_root=style_bundle_root, mode=mode)
    if not result["ok"]:
        raise ValueError(result["failure"]["failure_code"])
    selection = result["asset_selection"]
    declared_hash = page.get("resolved_asset_hash")
    if declared_hash and not str(declared_hash).startswith("[") and declared_hash != selection["resolved_asset_hash"]:
        raise ValueError("INVALID_RESOLVED_ASSET_HASH")
    declared_style_hash = page.get("style_master_content_hash")
    if declared_style_hash and not str(declared_style_hash).startswith("[") and declared_style_hash != selection["style_master_content_hash"]:
        raise ValueError("INVALID_STYLE_MASTER")
    return {"asset_selection": selection, "page_delta": page["page_delta"]}


def assemble_page_task(
    page: Mapping[str, Any],
    *,
    storyboard_page: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Assemble the text/reference task handed to the image-call host.

    Asset resolution remains the responsibility of ``build_page_prompt``.  This
    task carries the page's already-declared resolved binding and reference
    paths so a host can consume the same identity selection without rebuilding
    it.  The queue uses this lightweight boundary to bind page metadata and
    continuity reminders into the same claimed task without changing the legacy
    prompt return contract or calling an image model.
    """
    continuity_task = assemble_continuity_task(
        page,
        storyboard_page=storyboard_page,
        project_root=project_root,
    )
    continuity_review_record = build_continuity_review_record(
        page,
        continuity_task,
        discovery_stage="pre_generation",
        human_final_conclusion="pending",
        rework_needed="unknown",
    )
    return {
        "task_schema_version": 1,
        "page": page.get("page"),
        "page_id": page.get("page_id"),
        "page_version": page.get("page_version"),
        "prompt_path": page.get("current_prompt_path") or page.get("prompt_path"),
        "asset_binding": {
            "character_asset_bundle": page.get("character_asset_bundle"),
            "character_asset_version": page.get("character_asset_version"),
            "characters": page.get("characters"),
            "style_master_id": page.get("style_master_id"),
            "style_master_version": page.get("style_master_version"),
            "style_master_content_hash": page.get("style_master_content_hash"),
            "resolved_asset_hash": page.get("resolved_asset_hash"),
            "character_reference_path": page.get("character_reference_path"),
            "production_reference_path": page.get("production_reference_path"),
        },
        "page_delta": page.get("page_delta"),
        "visual_direction": _visual_direction(page, storyboard_page),
        "continuity_invariants": page.get("continuity_invariants"),
        "continuity_task": continuity_task,
        "continuity_review_record": continuity_review_record,
    }


def _declared_aspect(page: Mapping[str, Any]) -> float | None:
    value = page.get("declared_aspect_ratio", page.get("aspect_ratio"))
    if value is None:
        return None
    try:
        left, right = str(value).split(":", 1)
        ratio = float(left) / float(right)
    except (ValueError, ZeroDivisionError):
        raise ValueError("ASPECT_RATIO_MISMATCH") from None
    if ratio <= 0:
        raise ValueError("ASPECT_RATIO_MISMATCH")
    return ratio


def _minimum_dimensions(page: Mapping[str, Any]) -> tuple[int, int]:
    if page.get("profile") == "xiaohongshu-feed-3x4":
        return 1080, 1440
    return 1, 1


def complete_page(page: Mapping[str, Any], image_path: str | Path, *, mode: str = "production") -> dict[str, Any]:
    if validate_page_spec(page, mode=mode):
        raise ValueError("INVALID_PAGE_SPEC")
    path = Path(image_path)
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            bands = image.getbands()
            has_transparency = "A" in bands or "transparency" in image.info
    except (OSError, UnidentifiedImageError, SyntaxError, ValueError):
        raise ValueError("INVALID_IMAGE") from None
    minimum_width, minimum_height = _minimum_dimensions(page)
    if width < minimum_width or height < minimum_height:
        raise ValueError("INVALID_DIMENSIONS")
    declared = _declared_aspect(page)
    if page.get("profile") == "xiaohongshu-feed-3x4" and declared is None:
        declared = 3 / 4
    if declared is not None and abs((width / height) - declared) > 0.01:
        raise ValueError("ASPECT_RATIO_MISMATCH")
    if page.get("profile") == "xiaohongshu-feed-3x4" and (width, height) != (1080, 1440):
        raise ValueError("INVALID_DIMENSIONS")
    if page.get("profile") == "xiaohongshu-feed-3x4" and has_transparency:
        with Image.open(path) as image:
            if "A" in image.getbands() and image.getchannel("A").getextrema() == (255, 255):
                pass
            else:
                raise ValueError("INVALID_ALPHA")
    return {"status": "completed", "page_id": page["page_id"], "image_path": path.as_posix(), "dimensions": [width, height]}


def validate_legacy_page(manifest: Mapping[str, Any]) -> list[str]:
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1:
        return ["schema_version"]
    return [] if _nonempty(manifest.get("book_id")) and isinstance(manifest.get("pages"), list) else ["legacy manifest"]


def failure_event(failure_code: str, *, page_id: str, revision: int, recovery_advice: str | None = None) -> dict[str, Any]:
    advice = recovery_advice or {"MISSING_ASSET": "Select an approved asset ID and retry the page.", "INCOMPATIBLE_ASSET": "Choose an asset compatible with the selected character.", "REFERENCE_NOT_FOUND": "Restore the approved project-local reference file."}.get(failure_code, "Correct the page binding and retry the page.")
    return {"failure_code": failure_code, "page_id": page_id, "revision": revision, "recovery_advice": advice}

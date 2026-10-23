"""Determine page-local redraw work from image dependencies, not text edits."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


IMAGE_DEPENDENCY_FIELDS = ("character_asset_bundle", "character_asset_version", "characters", "style_master_id", "style_master_version", "style_master_content_hash", "page_delta", "source_prompt_hash", "resolved_asset_hash", "shot_id", "interaction_id", "family_interaction_id")
OPTIONAL_IMAGE_DEPENDENCY_FIELDS = ("scene_ref", "props", "asset_refs", "character_reference_assets", "continuity_invariants")


def image_dependency_fingerprint(page: Mapping[str, Any]) -> str:
    payload = {field: page.get(field) for field in IMAGE_DEPENDENCY_FIELDS}
    for field in OPTIONAL_IMAGE_DEPENDENCY_FIELDS:
        if field in page:
            payload[field] = page[field]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def affected_pages(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    old = {page.get("page_id"): page for page in before}
    redraw, text_only = [], []
    for page in after:
        page_id = page.get("page_id")
        previous = old.get(page_id)
        if previous is None or previous.get("page_version") != page.get("page_version") or image_dependency_fingerprint(previous) != image_dependency_fingerprint(page):
            redraw.append(page_id)
        elif previous.get("text") != page.get("text"):
            text_only.append(page_id)
    return {"image_redraw": redraw, "text_only": text_only}

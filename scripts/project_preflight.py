"""Read-only project contract and two-stage preflight checks.

This module deliberately does not create a queue, modify a project, or call an
image model.  It reuses the delivery contract, page-manifest validator,
generation plan builder, and continuity contract already used by production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from build_pure_image_delivery import (
    DeliveryError,
    _book_dir,
    _book_key,
    _canonical_hash,
    _inspect_image,
    _load_delivery_contract,
    _project_root,
    _resolve_content_layout,
    _source_image,
)
from continuity_contract import validate_continuity_invariants
from generation_queue import _plan
from validate_page_manifest import validate_page_manifest


SCHEMA_VERSION = 1
MODES = {"report-only", "strict"}
PHASES = {"pre_generation", "pre_delivery"}
AGES = {"3-4", "5-7", "8-10", "5-6"}
APPROVED_STATUSES = {"approved", "user_approved", "released"}
DELIVERY_REQUIRED_FILES = {
    "storyboard.json",
    "page-manifest.json",
    "page-text.json",
    "layout.json",
    "education-goal.json",
    "asset-binding-plan.json",
}


class PreflightError(ValueError):
    """A deterministic project preflight failure."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"JSON object required: {path}")
    return value


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_local_reference(value: Any, *, book_dir: Path, content_dir: Path, root: Path) -> Path | None:
    """Resolve project references used by historical and content layouts."""
    if not _nonempty(value):
        return None
    raw = str(value)
    candidate = Path(raw)
    choices = [candidate] if candidate.is_absolute() else [book_dir / candidate, content_dir / candidate, root / candidate]
    for item in choices:
        resolved = item.resolve()
        if resolved.is_file() or resolved.is_dir():
            return resolved
    return choices[0].resolve() if choices else None


def _page_map(data: Mapping[str, Any], label: str) -> dict[int, dict[str, Any]]:
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise PreflightError(f"{label}_PAGES_MISSING")
    result: dict[int, dict[str, Any]] = {}
    for index, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            raise PreflightError(f"{label}_PAGE_INVALID:{index}")
        try:
            number = int(page.get("page", index))
        except (TypeError, ValueError) as exc:
            raise PreflightError(f"{label}_PAGE_NUMBER_INVALID:{index}") from exc
        if number in result:
            raise PreflightError(f"{label}_DUPLICATE_PAGE:{number}")
        result[number] = page
    return result


def _metadata_values(documents: Iterable[Mapping[str, Any]], *keys: str) -> set[str]:
    result: set[str] = set()
    for document in documents:
        for key in keys:
            value = document.get(key)
            if _nonempty(value):
                result.add(str(value).strip())
    return result


def _find_approval(content_dir: Path, *, kind: str, bundle: str, style_id: str | None = None, style_version: str | None = None) -> Path | None:
    if kind == "character":
        aliases = [bundle]
        if bundle.startswith("core-characters-"):
            aliases.append("core-" + bundle.removeprefix("core-characters-"))
        candidates = [content_dir / "characters" / alias / "approval.json" for alias in aliases]
    else:
        slug = (style_id or "").strip().lower()
        version = (style_version or "").strip()
        candidates = [
            content_dir / "styles" / f"{slug}-{version}" / "approval.json",
            content_dir / "styles" / f"{slug}-{version.replace('.', '')}" / "approval.json",
        ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _approval_is_valid(path: Path, *, kind: str) -> tuple[bool, str]:
    try:
        data = _read_json(path)
    except PreflightError as exc:
        return False, str(exc)
    if kind == "character":
        status = data.get("formal_production_approval", {})
        approved = (
            isinstance(status, Mapping)
            and status.get("status") == "approved"
            and data.get("release_status") == "released"
            and data.get("production_enabled") is True
        )
    else:
        approved = (
            data.get("visual_approval_status") == "approved"
            and data.get("formal_production_approval_status") == "approved"
            and data.get("production_enabled_for_explicit_selection") is True
        )
    return approved, "approved" if approved else "approval record is not formally approved"


def _asset_approval_check(
    *,
    content_dir: Path,
    manifest_pages: Mapping[int, Mapping[str, Any]],
    asset_plan: Mapping[str, Any] | None,
    project_data: Mapping[str, Any],
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[dict[str, Any]] = []
    bundles = {str(page.get("character_asset_bundle", "")).strip() for page in manifest_pages.values() if _nonempty(page.get("character_asset_bundle"))}
    character_versions = {str(page.get("character_asset_version", "")).strip() for page in manifest_pages.values() if _nonempty(page.get("character_asset_version"))}
    style_ids = {str(page.get("style_master_id", "")).strip() for page in manifest_pages.values() if _nonempty(page.get("style_master_id"))}
    style_versions = {str(page.get("style_master_version", "")).strip() for page in manifest_pages.values() if _nonempty(page.get("style_master_version"))}
    for key, values in (("character_asset_bundle", bundles), ("character_asset_version", character_versions), ("style_master_id", style_ids), ("style_master_version", style_versions)):
        if len(values) > 1:
            blockers.append(f"ASSET_VERSION_CONFLICT:{key}")
    if not bundles and not character_versions:
        warnings.append("ASSET_REFERENCE_UNDECLARED")
    for bundle in sorted(bundles):
        approval = _find_approval(content_dir, kind="character", bundle=bundle)
        if approval is None:
            warnings.append(f"CHARACTER_APPROVAL_NOT_LOCAL:{bundle}")
            continue
        valid, detail = _approval_is_valid(approval, kind="character")
        evidence.append({"kind": "character_approval", "path": str(approval), "status": detail})
        if not valid:
            blockers.append(f"CHARACTER_APPROVAL_INVALID:{bundle}")
    if style_ids or style_versions:
        approval = _find_approval(
            content_dir,
            kind="style",
            bundle="",
            style_id=next(iter(style_ids), None),
            style_version=next(iter(style_versions), None),
        )
        if approval is None:
            warnings.append(f"STYLE_APPROVAL_NOT_LOCAL:{next(iter(style_ids), 'unknown')}:{next(iter(style_versions), 'unknown')}")
        else:
            valid, detail = _approval_is_valid(approval, kind="style")
            evidence.append({"kind": "style_approval", "path": str(approval), "status": detail})
            if not valid:
                blockers.append("STYLE_APPROVAL_INVALID")
    if isinstance(asset_plan, Mapping):
        selected = asset_plan.get("user_selected_assets")
        if isinstance(selected, Mapping):
            for key, expected in (
                ("character_formal_production_approval", "approved"),
                ("style_formal_production_approval", "approved"),
                ("style_status", "approved"),
            ):
                if selected.get(key) not in (None, expected):
                    blockers.append(f"ASSET_PLAN_NOT_APPROVED:{key}")
            if selected.get("character_formal_production_approval") == "approved" or selected.get("style_formal_production_approval") == "approved":
                evidence.append({"kind": "asset_binding_plan", "status": "approved_inline"})
    def version_alias(value: Any) -> str:
        text = str(value or "").strip()
        for prefix in ("core-characters-", "core-"):
            if text.startswith(prefix):
                return text[len(prefix):]
        return text

    project_characters = project_data.get("characters_version")
    if _nonempty(project_characters) and character_versions and version_alias(project_characters) not in {version_alias(item) for item in character_versions}:
        blockers.append("PROJECT_CHARACTER_VERSION_CONFLICT")
    project_style = project_data.get("style_id")
    project_style_version = project_data.get("style_version")
    if _nonempty(project_style) and style_ids and str(project_style).strip() not in style_ids:
        blockers.append("PROJECT_STYLE_ID_CONFLICT")
    if _nonempty(project_style_version) and style_versions and str(project_style_version).strip() not in style_versions:
        blockers.append("PROJECT_STYLE_VERSION_CONFLICT")
    return blockers, warnings, evidence


def _research_check(
    *,
    root: Path,
    book_dir: Path,
    content_dir: Path,
    manifest: Mapping[str, Any],
    project_data: Mapping[str, Any],
    layout: str,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[dict[str, Any]] = []
    references: list[tuple[str, Any]] = [
        ("research_packet", manifest.get("research_packet_path")),
        ("knowledge_whitelist", manifest.get("knowledge_whitelist_path")),
        ("story_claim_trace", manifest.get("story_claim_trace_path")),
    ]
    source = project_data.get("source")
    if not any(_nonempty(value) for _, value in references) and isinstance(source, Mapping):
        references.append(("project_source", source.get("path")))
    found: dict[str, Path] = {}
    for name, value in references:
        if not _nonempty(value):
            continue
        resolved = _resolve_local_reference(value, book_dir=book_dir, content_dir=content_dir, root=root)
        if resolved is None or not resolved.exists():
            if name in {"research_packet", "project_source"}:
                blockers.append(f"RESEARCH_SOURCE_MISSING:{name}")
            else:
                blockers.append(f"RESEARCH_EVIDENCE_MISSING:{name}")
            continue
        if not _inside(resolved, root):
            blockers.append(f"RESEARCH_PATH_ESCAPES_PROJECT:{name}")
            continue
        found[name] = resolved
        evidence.append({"kind": name, "path": str(resolved), "sha256": _sha256(resolved) if resolved.is_file() else None})
    if not found:
        if layout == "version-root":
            warnings.append("RESEARCH_TRACE_LEGACY_UNDECLARED")
        else:
            blockers.append("RESEARCH_TRACE_UNAVAILABLE")
    if found.get("research_packet") and found["research_packet"].is_dir():
        packet = found["research_packet"]
        required = {"sources.json", "claims.json", "child_concepts.json"}
        missing = sorted(name for name in required if not (packet / name).is_file())
        if missing:
            blockers.append("RESEARCH_PACKET_INCOMPLETE:" + ",".join(missing))
    return blockers, warnings, evidence


def _path_safety_check(*, root: Path, book_dir: Path, content_dir: Path, pages: Mapping[int, Mapping[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    evidence: list[dict[str, Any]] = []
    for number, page in sorted(pages.items()):
        for field in ("current_prompt_path", "prompt_path", "character_reference_path", "production_reference_path", "current_image_path"):
            value = page.get(field)
            if not _nonempty(value):
                continue
            resolved = _resolve_local_reference(value, book_dir=book_dir, content_dir=content_dir, root=root)
            if resolved is None or not _inside(resolved, book_dir):
                blockers.append(f"PAGE_PATH_ESCAPES_BOOK:{number}:{field}")
            else:
                evidence.append({"kind": field, "page": number, "path": str(resolved), "exists": resolved.is_file()})
    return blockers, evidence


def _review_status_check(book_dir: Path, pages: Mapping[int, Mapping[str, Any]]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence: list[dict[str, Any]] = []
    review_path = book_dir / "review" / "review.json"
    if not review_path.is_file():
        warnings.append("HUMAN_REVIEW_RECORD_MISSING")
        return blockers, warnings, evidence
    try:
        review = _read_json(review_path)
    except PreflightError as exc:
        blockers.append(str(exc))
        return blockers, warnings, evidence
    page_rows = {int(item.get("page")): item for item in review.get("pages", []) if isinstance(item, Mapping) and str(item.get("page", "")).isdigit()}
    for number in pages:
        row = page_rows.get(number)
        if row and str(row.get("status", "")).lower() in {"failed", "generation_failed_timeout", "not_reviewable"}:
            blockers.append(f"PAGE_REVIEW_NOT_COMPLETE:{number}")
    if review.get("user_final_approval") not in {True, "approved", "approved_for_formal_use"}:
        warnings.append("HUMAN_FINAL_APPROVAL_NOT_ASSERTED")
    evidence.append({"kind": "review", "path": str(review_path), "status": review.get("overall_status", "unknown")})
    return blockers, warnings, evidence


def _formal_image_check(root: Path, book_dir: Path, contract: Any) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[str] = []
    evidence: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for page in contract.pages:
        number = int(page["page"])
        try:
            source = _source_image(root, book_dir, page, content_dir=contract.content_dir)
            width, height, sha = _inspect_image(source)
        except (DeliveryError, OSError, ValueError) as exc:
            blockers.append(f"FORMAL_IMAGE_INVALID:{number}:{exc}")
            continue
        try:
            from PIL import Image

            with Image.open(source) as image:
                mode = image.mode
                exact = image.size == (1080, 1440) and mode == "RGB" and "A" not in image.getbands()
        except OSError as exc:
            blockers.append(f"FORMAL_IMAGE_UNREADABLE:{number}:{exc}")
            continue
        if not exact:
            blockers.append(f"FORMAL_IMAGE_SPEC_INVALID:{number}:{width}x{height}:{mode}")
        record = {"page": number, "path": str(source), "sha256": sha, "size": [width, height], "mode": mode, "exact_spec": exact}
        records.append(record)
        evidence.append({"kind": "formal_image", **record})
    if len(records) != len(contract.pages):
        blockers.append("FORMAL_IMAGE_COUNT_MISMATCH")
    return blockers, evidence, records


def _candidate_formal_conflict(book_dir: Path, contract: Any) -> list[str]:
    blockers: list[str] = []
    candidates_root = book_dir / "review" / "recovery-candidates"
    if not candidates_root.is_dir():
        return blockers
    formal = {str(path.resolve()) for page in contract.pages for path in [_source_image(book_dir.parent.parent.parent, book_dir, page, content_dir=contract.content_dir)] if path.is_file()}
    for candidate in candidates_root.rglob("*"):
        if candidate.is_file() and str(candidate.resolve()) in formal:
            blockers.append(f"CANDIDATE_USED_AS_FORMAL:{candidate}")
    return blockers


def _output_target_check(output: str | Path | None, *, input_fingerprint: str | None = None) -> tuple[list[str], list[str]]:
    if output is None:
        return [], []
    path = Path(output).resolve()
    warnings: list[str] = []
    blockers: list[str] = []
    if path.exists() and not path.is_dir():
        blockers.append("DELIVERY_TARGET_NOT_DIRECTORY")
    if path.is_dir() and input_fingerprint:
        validation = path / "delivery-validation.json"
        if not validation.is_file():
            blockers.append("DELIVERY_TARGET_EXISTS_UNVERIFIED")
        else:
            try:
                data = _read_json(validation)
            except PreflightError as exc:
                blockers.append(str(exc))
            else:
                if data.get("input_fingerprint") != input_fingerprint:
                    blockers.append("DELIVERY_TARGET_DIFFERENT_INPUT")
                else:
                    warnings.append("DELIVERY_TARGET_CAN_REUSE")
    return blockers, warnings


def _delivery_fingerprint(root: Path, book_dir: Path, contract: Any, records: list[dict[str, Any]]) -> str:
    return _canonical_hash(
        {
            "output_mode": "pure-images",
            "canvas": [1080, 1440],
            "storyboard": contract.storyboard,
            "contract": {
                "layout": contract.layout,
                "business_book_id": contract.business_book_id,
                "age_band": contract.age_band,
                "input_hashes": contract.input_hashes,
            },
            "pages": [
                {"page": item["page"], "source_sha256": item["sha256"], "source_size": item["size"]}
                for item in records
            ],
        }
    )


def preflight_project(
    project: str | Path,
    book_id: str,
    *,
    version: str | None = None,
    phase: str = "pre_generation",
    mode: str = "report-only",
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Run a read-only preflight using one shared rule set for both modes."""
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {sorted(PHASES)}")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}")
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "phase": phase,
        "mode": mode,
        "project_root": None,
        "requested_book_id": book_id,
        "book_key": None,
        "version": version,
        "layout": None,
        "business_book_id": None,
        "age_band": None,
        "page_count": None,
        "passed": [],
        "warnings": [],
        "blockers": [],
        "evidence": [],
        "fix_advice": [],
        "write_operations": 0,
        "image_model_calls": 0,
        "host_status": "not_verified",
    }

    def passed(check: str, **fields: Any) -> None:
        report["passed"].append({"check": check, **fields})

    try:
        root = _project_root(project)
        book_key = _book_key(root, book_id)
        book_dir = _book_dir(root, book_id, version)
        content_dir, layout = _resolve_content_layout(book_dir)
    except (DeliveryError, OSError, ValueError) as exc:
        report["blockers"].append(f"PROJECT_RESOLUTION:{exc}")
        report["fix_advice"].append("确认 project.json、books/<book-key>/<version> 和内容布局唯一且可读。")
        return report

    report.update({"project_root": str(root), "book_key": book_key, "version": book_dir.name, "layout": layout})
    try:
        project_data = _read_json(root / "project.json")
    except PreflightError as exc:
        report["blockers"].append(f"PROJECT_METADATA_INVALID:{exc}")
        report["fix_advice"].append("修复 project.json 后重新运行同一阶段预检。")
        return report
    passed("project_resolved", path=str(root))

    try:
        contract = _load_delivery_contract(root, book_dir, book_id)
        manifest_path = content_dir / "page-manifest.json"
        manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
        storyboard = contract.storyboard
        manifest_pages = _page_map(manifest, "PAGE_MANIFEST") if manifest else {int(page["page"]): page for page in contract.pages}
        storyboard_pages = _page_map(storyboard, "STORYBOARD")
    except (DeliveryError, PreflightError, OSError, ValueError) as exc:
        report["blockers"].append(f"CONTRACT_INVALID:{exc}")
        report["fix_advice"].append("补齐或修复故事、分镜、页面清单和统一内容根目录中的契约文件。")
        return report

    report.update({"business_book_id": contract.business_book_id, "age_band": contract.age_band, "page_count": len(contract.pages)})
    passed("business_book_id_mapping", business_book_id=contract.business_book_id, book_key=book_key)

    books = project_data.get("books")
    if not isinstance(books, list):
        report["blockers"].append("PROJECT_BOOKS_INVALID")
    else:
        ids = [item.get("id") for item in books if isinstance(item, Mapping)]
        if len(ids) != len(set(ids)):
            report["blockers"].append("PROJECT_BOOK_ID_NOT_UNIQUE")
        else:
            passed("project_book_id_unique")

    metadata_documents: list[Mapping[str, Any]] = [project_data, contract.storyboard, manifest]
    for name in DELIVERY_REQUIRED_FILES:
        path = content_dir / name
        if layout == "content" and not path.is_file():
            report["blockers"].append(f"CONTRACT_FILE_MISSING:{name}")
        elif path.is_file():
            passed("contract_file_present", file=name, path=str(path))
    age_values = _metadata_values(metadata_documents, "age_band", "target_age_band")
    project_targets = project_data.get("target_age_bands")
    if isinstance(project_targets, list):
        age_values.update(str(value).strip() for value in project_targets if _nonempty(value))
    if any(value not in AGES for value in age_values):
        report["blockers"].append("AGE_BAND_INVALID")
    elif len(age_values) > 1:
        report["blockers"].append("AGE_BAND_CONFLICT")
    elif age_values:
        report["age_band"] = next(iter(age_values))
        passed("age_band_consistent", age_band=report["age_band"])
    else:
        report["warnings"].append("AGE_BAND_UNKNOWN")

    story_candidates = [content_dir / "story.md", book_dir / "story.md"]
    story_path = next((path for path in story_candidates if path.is_file()), None)
    if story_path is None or not story_path.read_text(encoding="utf-8").strip():
        report["blockers"].append("STORY_MISSING_OR_EMPTY")
    else:
        passed("story_complete", path=str(story_path))
    if set(manifest_pages) != set(storyboard_pages):
        report["blockers"].append("PAGE_NUMBER_SET_CONFLICT")
    else:
        passed("page_numbers_match", page_count=len(manifest_pages))
    for number, page in sorted(storyboard_pages.items()):
        if not _nonempty(page.get("text")):
            report["blockers"].append(f"PAGE_TEXT_MISSING:{number}")
    page_text_path = content_dir / "page-text.json"
    if page_text_path.is_file():
        page_text = _read_json(page_text_path)
        try:
            text_pages = _page_map(page_text, "PAGE_TEXT")
        except PreflightError as exc:
            report["blockers"].append(str(exc))
        else:
            if set(text_pages) != set(storyboard_pages):
                report["blockers"].append("PAGE_TEXT_PAGE_NUMBER_CONFLICT")
            for number, row in text_pages.items():
                if not _nonempty(row.get("text")):
                    report["blockers"].append(f"PAGE_TEXT_EMPTY:{number}")
                elif _nonempty(storyboard_pages[number].get("text")) and str(row["text"]).strip() != str(storyboard_pages[number]["text"]).strip():
                    report["blockers"].append(f"PAGE_TEXT_STORYBOARD_CONFLICT:{number}")
            if not report["blockers"] or not any(item.startswith("PAGE_TEXT_") for item in report["blockers"]):
                passed("page_text_matches_storyboard", path=str(page_text_path))
    elif phase == "pre_generation" and layout == "content":
        report["blockers"].append("PAGE_TEXT_MISSING")

    manifest_errors = validate_page_manifest(
        manifest,
        content_dir,
        require_images=phase == "pre_delivery",
        strict_assets=False,
    )
    for error in manifest_errors:
        report["blockers"].append(f"PAGE_MANIFEST:{error}")
    if not manifest_errors:
        passed("page_manifest_validation", require_images=phase == "pre_delivery")

    path_blocks, path_evidence = _path_safety_check(root=root, book_dir=book_dir, content_dir=content_dir, pages=manifest_pages)
    report["blockers"].extend(path_blocks)
    report["evidence"].extend(path_evidence)
    if not path_blocks:
        passed("project_path_safety")

    asset_plan_path = content_dir / "asset-binding-plan.json"
    try:
        asset_plan = _read_json(asset_plan_path) if asset_plan_path.is_file() else None
    except PreflightError as exc:
        report["blockers"].append(f"ASSET_PLAN_INVALID:{exc}")
        asset_plan = None
    asset_blocks, asset_warnings, asset_evidence = _asset_approval_check(
        content_dir=content_dir,
        manifest_pages=manifest_pages,
        asset_plan=asset_plan,
        project_data=project_data,
    )
    report["blockers"].extend(asset_blocks)
    report["warnings"].extend(asset_warnings)
    report["evidence"].extend(asset_evidence)
    if not asset_blocks:
        passed("approved_asset_and_style_references", warnings=asset_warnings)

    research_blocks, research_warnings, research_evidence = _research_check(
        root=root,
        book_dir=book_dir,
        content_dir=content_dir,
        manifest=manifest,
        project_data=project_data,
        layout=layout,
    )
    report["blockers"].extend(research_blocks)
    report["warnings"].extend(research_warnings)
    report["evidence"].extend(research_evidence)
    if not research_blocks:
        passed("research_traceability", warnings=research_warnings)

    continuity_blocks: list[str] = []
    continuity_warnings: list[str] = []
    for number, page in sorted(manifest_pages.items()):
        continuity = validate_continuity_invariants(page, project_root=content_dir)
        continuity_blocks.extend(f"{number}:{item['code']}" for item in continuity["blocks"])
        continuity_warnings.extend(f"{number}:{item['code']}" for item in continuity["warnings"])
    report["blockers"].extend(f"CONTINUITY_BLOCK:{item}" for item in continuity_blocks)
    report["warnings"].extend(f"CONTINUITY_WARN:{item}" for item in continuity_warnings)
    if not continuity_blocks:
        passed("continuity_contract", warnings=continuity_warnings)

    plan = None
    try:
        plan = _plan(content_dir if layout == "content" else book_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["blockers"].append(f"TASK_ASSEMBLY:{exc}")
    else:
        passed("page_task_assembly", page_count=plan.get("page_count"), plan_fingerprint=plan.get("plan_fingerprint"))
        report["evidence"].append({"kind": "plan", "page_count": plan.get("page_count"), "plan_fingerprint": plan.get("plan_fingerprint")})

    if phase == "pre_delivery":
        image_blocks, image_evidence, image_records = _formal_image_check(root, book_dir, contract)
        report["blockers"].extend(image_blocks)
        report["evidence"].extend(image_evidence)
        delivery_fingerprint = _delivery_fingerprint(root, book_dir, contract, image_records) if len(image_records) == len(contract.pages) else None
        if delivery_fingerprint:
            report["evidence"].append({"kind": "delivery_input_fingerprint", "value": delivery_fingerprint})
            target_blocks, target_warnings = _output_target_check(output, input_fingerprint=delivery_fingerprint)
            report["blockers"].extend(target_blocks)
            report["warnings"].extend(target_warnings)
        review_blocks, review_warnings, review_evidence = _review_status_check(book_dir, manifest_pages)
        report["blockers"].extend(review_blocks)
        report["warnings"].extend(review_warnings)
        report["evidence"].extend(review_evidence)
        try:
            candidate_blocks = _candidate_formal_conflict(book_dir, contract)
        except (DeliveryError, OSError, ValueError) as exc:
            candidate_blocks = [f"CANDIDATE_SCAN_FAILED:{exc}"]
        report["blockers"].extend(candidate_blocks)
        if not image_blocks and not candidate_blocks:
            passed("formal_images_and_candidate_separation", page_count=len(contract.pages))
        if not review_blocks:
            passed("human_review_record_check", warnings=review_warnings)
    else:
        if output is not None:
            target_blocks, target_warnings = _output_target_check(output)
            report["blockers"].extend(target_blocks)
            report["warnings"].extend(target_warnings)

    report["status"] = "passed" if not report["blockers"] else "blocked"
    if report["status"] == "passed":
        report["fix_advice"] = ["继续保留人工科学、无字和视觉审核；自动预检不等同人工批准。"]
    else:
        report["fix_advice"].append("修复 blockers 后重新运行同一阶段预检；严格模式不会自动修复或创建队列。")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("book_id")
    parser.add_argument("--version")
    parser.add_argument("--phase", choices=sorted(PHASES), default="pre_generation")
    parser.add_argument("--mode", choices=sorted(MODES), default="report-only")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = preflight_project(
            args.project,
            args.book_id,
            version=args.version,
            phase=args.phase,
            mode=args.mode,
        )
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0 if report["status"] == "passed" else 2 if args.mode == "strict" else 0
    except (OSError, ValueError, PreflightError) as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

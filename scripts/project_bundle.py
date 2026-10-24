"""Read-only checks for production dependency closures and project profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


PRODUCTION_PROFILES = {"delivery-only", "production-ready"}
PAGE_DEPENDENCY_FIELDS = (
    "current_prompt_path",
    "prompt_path",
    "character_reference_path",
    "production_reference_path",
)
PROJECT_DEPENDENCY_FIELDS = (
    "research_packet_path",
    "knowledge_whitelist_path",
    "story_claim_trace_path",
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_existing(value: str, *, book_dir: Path, content_dir: Path, root: Path) -> tuple[Path | None, str]:
    candidate = Path(value)
    choices = [candidate] if candidate.is_absolute() else [book_dir / candidate, content_dir / candidate, root / candidate]
    for item in choices:
        resolved = item.resolve()
        if resolved.is_file() or resolved.is_dir():
            return resolved, "resolved"
    return choices[0].resolve() if choices else None, "missing"


def _record_missing(records: list[dict[str, Any]], *, page: int | None, field: str, value: str, scope: str) -> None:
    records.append({"page": page, "field": field, "value": value, "scope": scope})


def validate_production_dependencies(
    *,
    book_dir: str | Path,
    content_dir: str | Path,
    root: str | Path,
    pages: Mapping[int, Mapping[str, Any]],
    manifest: Mapping[str, Any],
    project_data: Mapping[str, Any],
    phase: str,
) -> dict[str, Any]:
    """Validate the files required to resume or produce a book.

    The function is deliberately read-only. It distinguishes a delivery-only
    bundle from a production-ready bundle without changing the schema of any
    existing project contract.
    """

    book_root = Path(book_dir).resolve()
    content_root = Path(content_dir).resolve()
    project_root = Path(root).resolve()
    explicit_profile = str(project_data.get("project_profile", "")).strip() or None
    profile = explicit_profile if explicit_profile in PRODUCTION_PROFILES else None
    required: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    outside_book: list[dict[str, Any]] = []
    warnings: list[str] = []
    evidence: list[dict[str, Any]] = []

    for number, page in sorted(pages.items()):
        prompt_field = "current_prompt_path" if _nonempty(page.get("current_prompt_path")) else "prompt_path"
        prompt_value = page.get(prompt_field)
        if not _nonempty(prompt_value):
            _record_missing(missing, page=number, field="current_prompt_path", value="", scope="book")
        else:
            item = {"page": number, "field": prompt_field, "value": str(prompt_value), "scope": "book"}
            required.append(item)
            resolved, resolution = _resolve_existing(str(prompt_value), book_dir=book_root, content_dir=content_root, root=project_root)
            if resolved is None or resolution == "missing":
                missing.append(item)
            elif not _inside(resolved, book_root):
                outside_book.append({**item, "resolved": str(resolved)})
            else:
                evidence.append({**item, "resolved": str(resolved)})

        for field in ("character_reference_path", "production_reference_path"):
            value = page.get(field)
            if not _nonempty(value):
                _record_missing(missing, page=number, field=field, value="", scope="book")
                continue
            item = {"page": number, "field": field, "value": str(value), "scope": "book"}
            required.append(item)
            resolved, resolution = _resolve_existing(str(value), book_dir=book_root, content_dir=content_root, root=project_root)
            if resolved is None or resolution == "missing":
                missing.append(item)
            elif not _inside(resolved, book_root):
                outside_book.append({**item, "resolved": str(resolved)})
            else:
                evidence.append({**item, "resolved": str(resolved)})

        current_image = page.get("current_image_path")
        if _nonempty(current_image):
            item = {"page": number, "field": "current_image_path", "value": str(current_image), "scope": "book", "optional_before_delivery": phase == "pre_generation"}
            required.append(item)
            resolved, resolution = _resolve_existing(str(current_image), book_dir=book_root, content_dir=content_root, root=project_root)
            if resolution == "missing" and phase == "pre_delivery":
                missing.append(item)
            elif resolved is not None and _inside(resolved, book_root):
                evidence.append({**item, "resolved": str(resolved)})
            elif resolved is not None:
                outside_book.append({**item, "resolved": str(resolved)})

    for field in PROJECT_DEPENDENCY_FIELDS:
        value = manifest.get(field)
        if not _nonempty(value):
            continue
        item = {"page": None, "field": field, "value": str(value), "scope": "project"}
        required.append(item)
        resolved, resolution = _resolve_existing(str(value), book_dir=book_root, content_dir=content_root, root=project_root)
        if resolved is None or resolution == "missing":
            missing.append(item)
        elif not _inside(resolved, project_root):
            outside_book.append({**item, "resolved": str(resolved), "reason": "outside_project"})
        else:
            evidence.append({**item, "resolved": str(resolved)})

    if explicit_profile and explicit_profile not in PRODUCTION_PROFILES:
        warnings.append(f"PROJECT_PROFILE_UNKNOWN:{explicit_profile}")
    if profile == "delivery-only":
        status = "blocked" if phase == "pre_generation" else "passed"
        if phase == "pre_generation":
            warnings.append("PROJECT_PROFILE_DELIVERY_ONLY")
    elif missing or outside_book:
        status = "blocked"
        if profile is None:
            profile = "legacy-undeclared"
    else:
        status = "passed"
        if profile is None:
            profile = "production-ready"

    return {
        "status": status,
        "profile": profile or "legacy-undeclared",
        "phase": phase,
        "required": required,
        "missing": missing,
        "outside_book": outside_book,
        "warnings": warnings,
        "evidence": evidence,
    }

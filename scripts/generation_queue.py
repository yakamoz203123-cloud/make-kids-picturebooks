"""Resumable, page-scoped production queue for picturebook image generation.

This module deliberately does not call an image API.  The host image tool owns
generation; this queue owns the book plan, one job per page, bounded claims,
atomic state, cache checks, retries, and page-local revisions.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from PIL import Image

from build_pure_image_delivery import _resolve_content_layout
from page_production import assemble_page_task
from page_versions import IMAGE_DEPENDENCY_FIELDS, OPTIONAL_IMAGE_DEPENDENCY_FIELDS, image_dependency_fingerprint


SCHEMA_VERSION = 1
REQUEST_LIFECYCLE_SCHEMA_VERSION = 1
DEFAULT_MAX_IN_FLIGHT = 2
DEFAULT_MAX_ATTEMPTS = 2
MIN_IMAGE_SIDE_PX = 1024
COORDINATION_MODE = "single-coordinator"
QUEUE_LOCK_TIMEOUT_SECONDS = 5.0
QUEUE_LOCK_POLL_SECONDS = 0.05
QUEUE_LOCK_STALE_SECONDS = 300.0
ACTIVE_STATUSES = {"running"}
DONE_STATUSES = {"completed", "cached"}
RETRYABLE_STATUSES = {"pending", "retryable"}
REQUEST_STATES = {"running", "succeeded", "failed", "pending_unknown", "timed_out"}
UNKNOWN = "unknown"
COST_UNKNOWN = "cost_unknown"
LIFECYCLE_ENFORCED_FIELD = "lifecycle_enforced"
SOCIAL_PROFILE_ASPECT_RATIOS = {
    "xiaohongshu-feed-3x4": "3:4",
    "social-vertical-9x16": "9:16",
}
SOCIAL_PROFILE_CANVASES = {
    "xiaohongshu-feed-3x4": (1080, 1440),
    "social-vertical-9x16": (1080, 1920),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _queue_lock_path(queue_path: Path) -> Path:
    return Path(f"{queue_path}.lock")


def _pid_is_alive(pid: int) -> bool:
    """Return whether a process id appears to be alive on this host."""
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_record(lock_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = lock_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None, None
    try:
        record = json.loads(raw)
    except json.JSONDecodeError:
        return None, raw
    return (record if isinstance(record, dict) else None), raw


def _unlink_lock_if_unchanged(lock_path: Path, expected_raw: str | None) -> bool:
    """Best-effort compare-before-delete for a stale lock file."""
    record, current_raw = _read_lock_record(lock_path)
    del record
    if current_raw != expected_raw:
        return False
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return False
    return True


@contextmanager
def _queue_mutation_lock(queue_path: Path):
    """Serialize queue read-modify-write operations with a stdlib lock file."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _queue_lock_path(queue_path)
    deadline = time.monotonic() + QUEUE_LOCK_TIMEOUT_SECONDS
    owner_token = uuid.uuid4().hex
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(
                        {
                            "pid": os.getpid(),
                            "created_at": _now(),
                            "mode": COORDINATION_MODE,
                            "owner_token": owner_token,
                        },
                        handle,
                        ensure_ascii=False,
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                raise
            break
        except FileExistsError:
            try:
                lock_stat = lock_path.stat()
            except FileNotFoundError:
                continue
            stale = time.time() - lock_stat.st_mtime > QUEUE_LOCK_STALE_SECONDS
            if stale:
                record, raw = _read_lock_record(lock_path)
                owner_pid = record.get("pid") if record else None
                # A stale timestamp alone is not enough: a long-running live
                # coordinator must keep its lock.  Old/malformed lock files
                # have no owner to prove liveness, so they remain reclaimable.
                if owner_pid is None or not _pid_is_alive(owner_pid):
                    _unlink_lock_if_unchanged(lock_path, raw)
                    continue
            if time.monotonic() >= deadline:
                raise RuntimeError(f"queue is locked by another coordinator: {lock_path}")
            time.sleep(QUEUE_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        record, _ = _read_lock_record(lock_path)
        if record and record.get("owner_token") == owner_token:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _image_page_inputs(page: dict[str, Any]) -> dict[str, Any]:
    """Keep image-affecting page fields separate from text/layout metadata."""
    fields = tuple(dict.fromkeys((*IMAGE_DEPENDENCY_FIELDS, *OPTIONAL_IMAGE_DEPENDENCY_FIELDS,
        "current_prompt_path",
        "prompt_path",
        "character_reference_path",
        "production_reference_path",
        "characters_version",
        "source_aspect_ratio",
    )))
    return {field: page.get(field) for field in fields if field in page}


def _layout_image_inputs(
    layout_page: dict[str, Any] | None,
    *,
    style_version: str | None,
    declared_aspect_ratio: str | None,
) -> dict[str, Any]:
    """Return only deterministic layout values that can affect the source image."""
    if not isinstance(layout_page, dict):
        return {
            "style_version": style_version,
            "source_aspect_ratio": declared_aspect_ratio,
        }

    social_layouts: list[dict[str, Any]] = []
    containers = [layout_page]
    nested_design = layout_page.get("layout_design")
    if isinstance(nested_design, dict):
        containers.append(nested_design)
    for container in containers:
        social_layout = container.get("social_layout")
        if isinstance(social_layout, dict):
            social_layouts.append(social_layout)

    profiles = sorted(
        {
            str(value).strip()
            for social_layout in social_layouts
            for value in (social_layout.get("profile"),)
            if isinstance(value, str) and value.strip()
        }
    )
    composition_modes = sorted(
        {
            str(value).strip()
            for social_layout in social_layouts
            for value in (social_layout.get("composition_mode"),)
            if isinstance(value, str) and value.strip()
        }
    )
    layout_style_version = layout_page.get("layout_style_version")
    if not isinstance(layout_style_version, str) and isinstance(nested_design, dict):
        layout_style_version = nested_design.get("layout_style_version")
    result: dict[str, Any] = {
        "style_version": style_version,
        "layout_style_version": layout_style_version,
        "source_aspect_ratio": declared_aspect_ratio,
    }
    if profiles:
        result["social_profiles"] = profiles
    if composition_modes:
        result["social_composition_modes"] = composition_modes
    return result


def _asset_dependency_fingerprint(
    page: dict[str, Any],
    *,
    storyboard_page: dict[str, Any] | None = None,
    layout_page: dict[str, Any] | None = None,
    prompt_hash: str,
    character_hash: str,
    production_hash: str,
    style_version: str | None,
    declared_aspect_ratio: str | None,
    reference_assets: list[dict[str, Any]] | None = None,
) -> str:
    """Return a stable fingerprint for every resolved image input on a page."""
    storyboard_inputs = storyboard_page if isinstance(storyboard_page, dict) else {}
    return _canonical_hash(
        {
            "manifest_page_image_dependencies": image_dependency_fingerprint(page),
            "storyboard_page_image_dependencies": image_dependency_fingerprint(storyboard_inputs),
            "manifest_page_inputs": _image_page_inputs(page),
            "storyboard_page_inputs": _image_page_inputs(storyboard_inputs),
            "prompt_hash": prompt_hash,
            "character_reference_hash": character_hash,
            "production_reference_hash": production_hash,
            "layout_image_inputs": _layout_image_inputs(
                layout_page,
                style_version=style_version,
                declared_aspect_ratio=declared_aspect_ratio,
            ),
            "page_reference_assets": reference_assets or [],
        }
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_reference_assets(book_dir: Path, page: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve optional page-local supplemental references and verify their hashes."""
    raw = page.get("character_reference_assets")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("character_reference_assets must be a list")
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(raw):
        if not isinstance(record, dict):
            raise ValueError(f"character_reference_assets[{index}] must be an object")
        path_value = record.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError(f"character_reference_assets[{index}] is missing path")
        path = _resolve_book_path(book_dir, path_value)
        if path is None or not path.is_file():
            raise ValueError(f"character reference asset does not exist: {path_value}")
        relative = Path(path_value.replace("\\", "/")).as_posix()
        if relative in seen:
            raise ValueError(f"duplicate character reference asset path: {relative}")
        seen.add(relative)
        actual_hash = _file_hash(path)
        declared_hash = record.get("sha256")
        if declared_hash is not None and (not isinstance(declared_hash, str) or declared_hash.lower() != actual_hash):
            raise ValueError(f"character reference asset hash mismatch: {path_value}")
        resolved.append({
            "asset_id": str(record.get("asset_id") or ""),
            "path": relative,
            "sha256": actual_hash,
            "reference_purpose": str(record.get("reference_purpose") or "auxiliary-reference"),
        })
    return resolved


def _parse_aspect_ratio(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or ":" not in value:
        raise ValueError(f"invalid declared aspect ratio: {value!r}")
    numerator_text, denominator_text = value.split(":", 1)
    try:
        numerator = int(numerator_text)
        denominator = int(denominator_text)
    except ValueError as exc:
        raise ValueError(f"invalid declared aspect ratio: {value!r}") from exc
    if numerator <= 0 or denominator <= 0:
        raise ValueError(f"invalid declared aspect ratio: {value!r}")
    return numerator, denominator


def _validate_image_file(
    path: Path,
    declared_aspect_ratio: str | None = None,
    expected_canvas: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Verify, reopen, fully decode, and validate one generated image."""
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise ValueError(f"output is not a valid image: {path}") from exc

    try:
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format
            image.load()
    except Exception as exc:
        raise ValueError(f"output is not a valid image: {path}") from exc

    if width < MIN_IMAGE_SIDE_PX or height < MIN_IMAGE_SIDE_PX:
        raise ValueError(
            f"output image must be at least {MIN_IMAGE_SIDE_PX}px on both sides: "
            f"{width}x{height}"
        )
    if declared_aspect_ratio is not None:
        numerator, denominator = _parse_aspect_ratio(declared_aspect_ratio)
        if width * denominator != height * numerator:
            raise ValueError(
                f"output image aspect ratio must be {declared_aspect_ratio}: {width}x{height}"
            )
    if expected_canvas is not None and (width, height) != expected_canvas:
        expected_width, expected_height = expected_canvas
        raise ValueError(
            "output image exact canvas is "
            f"{width}x{height}; expected {expected_width}x{expected_height}"
        )
    divisor = math.gcd(width, height)
    return {
        "width_px": width,
        "height_px": height,
        "format": image_format,
        "aspect_ratio": f"{width // divisor}:{height // divisor}",
    }


def _resolve_contained_path(book_dir: Path, candidate: Path) -> Path:
    book_root = book_dir.resolve()
    resolved = (book_root / candidate).resolve()
    try:
        resolved.relative_to(book_root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside book directory: {candidate}") from exc
    return resolved


def _resolve_book_path(book_dir: Path, relative_or_absolute: str | None) -> Path | None:
    """Resolve a project input path and reject absolute/traversal/symlink escapes."""
    if not relative_or_absolute:
        return None
    raw = str(relative_or_absolute)
    normalized = raw.replace("\\", "/")
    posix_candidate = PurePosixPath(normalized)
    windows_candidate = PureWindowsPath(raw)
    if posix_candidate.is_absolute() or windows_candidate.is_absolute() or windows_candidate.drive:
        raise ValueError(f"input path must be relative to book directory: {relative_or_absolute}")
    if ".." in posix_candidate.parts or ".." in windows_candidate.parts:
        raise ValueError(f"input path must not contain '..': {relative_or_absolute}")
    candidate = Path(normalized)
    return _resolve_contained_path(book_dir, candidate)


def _resolve_output_path(book_dir: Path, relative_or_absolute: str | None) -> Path | None:
    """Preserve the historical output-path resolution before relative validation."""
    if not relative_or_absolute:
        return None
    candidate = Path(relative_or_absolute)
    if not candidate.is_absolute():
        candidate = book_dir / candidate
    return candidate.resolve()


def _relative_to_book(book_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(book_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path must stay inside book directory: {path}") from exc


def _story_dependency_value(page: dict[str, Any]) -> Any:
    if "story_dependency" in page and page["story_dependency"] is not None:
        return page["story_dependency"]
    return None


def _story_dependency_segment(
    story_text: str,
    book_dir: Path,
    story_path: Path,
    dependency: Any,
) -> str | None:
    """Resolve a declared page dependency or return None for conservative fallback.

    Supported declarations are exact unique text, inclusive line ranges, and a
    text/excerpt field.  Unsupported or ambiguous declarations deliberately
    fall back to the whole story instead of weakening cache invalidation.
    """
    source_text = story_text
    descriptor = dependency
    if isinstance(dependency, dict) and dependency.get("path"):
        source = _resolve_book_path(book_dir, str(dependency["path"]))
        if source is None or not source.is_file():
            return None
        try:
            source_text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None
        descriptor = {key: value for key, value in dependency.items() if key != "path"}

    if isinstance(descriptor, str):
        needle = descriptor.strip()
        if not needle or needle in {"story.md", "whole-story"}:
            return None
        return needle if source_text.count(needle) == 1 else None

    if isinstance(descriptor, dict):
        lines = descriptor.get("lines")
        if lines is not None:
            if (
                not isinstance(lines, list)
                or len(lines) != 2
                or not all(type(value) is int for value in lines)
            ):
                return None
            start, end = lines
        else:
            start = descriptor.get("line_start")
            end = descriptor.get("line_end")
        if start is not None or end is not None:
            if lines is not None and ("line_start" in descriptor or "line_end" in descriptor):
                return None
            if type(start) is not int or type(end) is not int or start < 1 or end < start:
                return None
            source_lines = source_text.splitlines(keepends=True)
            if end > len(source_lines):
                return None
            return "".join(source_lines[start - 1 : end])

        excerpt = descriptor.get("excerpt", descriptor.get("text"))
        if isinstance(excerpt, str) and excerpt.strip() and source_text.count(excerpt) == 1:
            return excerpt

        section = descriptor.get("section")
        if isinstance(section, str) and section.strip():
            target = section.strip().lstrip("#").strip()
            source_lines = source_text.splitlines(keepends=True)
            start_index = None
            for index, line in enumerate(source_lines):
                if line.lstrip().startswith("#") and line.lstrip().lstrip("#").strip() == target:
                    start_index = index
                    break
            if start_index is None:
                return None
            end_index = len(source_lines)
            for index in range(start_index + 1, len(source_lines)):
                if source_lines[index].lstrip().startswith("#"):
                    end_index = index
                    break
            return "".join(source_lines[start_index:end_index])

    if isinstance(descriptor, list) and descriptor:
        segments = [_story_dependency_segment(story_text, book_dir, story_path, item) for item in descriptor]
        if all(segment is not None for segment in segments):
            return "\n".join(segment for segment in segments if segment is not None)
    return None


def _story_dependency_fingerprint(
    story_text: str,
    story_path: Path,
    book_dir: Path,
    dependencies: list[Any],
    whole_story_sha256: str,
) -> tuple[str, str]:
    present = [dependency for dependency in dependencies if dependency is not None]
    if not present:
        return "whole-story", whole_story_sha256

    parts = []
    for dependency in present:
        segment = _story_dependency_segment(story_text, book_dir, story_path, dependency)
        if isinstance(dependency, str) and dependency.strip() in {"story.md", "whole-story"}:
            return "whole-story", whole_story_sha256
        if isinstance(dependency, dict) and dependency.get("mode") in {"book", "whole-story"}:
            return "whole-story", whole_story_sha256
        if segment is None:
            return "whole-story", whole_story_sha256
        parts.append({"dependency": dependency, "resolved_segment": segment})
    return "page", _canonical_hash(parts)


def _declared_aspect_ratio(*pages: dict[str, Any]) -> str | None:
    values: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        candidates: list[Any] = [page.get("source_aspect_ratio")]
        social_layout = page.get("social_layout")
        if isinstance(social_layout, dict):
            candidates.append(social_layout.get("source_aspect_ratio"))
            profile = social_layout.get("profile")
            if profile in SOCIAL_PROFILE_ASPECT_RATIOS:
                candidates.append(SOCIAL_PROFILE_ASPECT_RATIOS[profile])
        layout_design = page.get("layout_design")
        if isinstance(layout_design, dict):
            nested_social = layout_design.get("social_layout")
            if isinstance(nested_social, dict):
                candidates.append(nested_social.get("source_aspect_ratio"))
                profile = nested_social.get("profile")
                if profile in SOCIAL_PROFILE_ASPECT_RATIOS:
                    candidates.append(SOCIAL_PROFILE_ASPECT_RATIOS[profile])
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                normalized = candidate.strip()
                _parse_aspect_ratio(normalized)
                values.append(normalized)
    distinct = set(values)
    if len(distinct) > 1:
        raise ValueError(f"page declares conflicting aspect ratios: {sorted(distinct)}")
    return values[0] if values else None


def _declared_canvas(*pages: dict[str, Any]) -> tuple[int, int] | None:
    values: list[tuple[int, int]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        containers = [page]
        nested_layout = page.get("layout_design")
        if isinstance(nested_layout, dict):
            containers.append(nested_layout)
        for container in containers:
            social_layout = container.get("social_layout")
            if isinstance(social_layout, dict):
                containers.append(social_layout)
            profile = container.get("profile")
            if profile in SOCIAL_PROFILE_CANVASES:
                values.append(SOCIAL_PROFILE_CANVASES[profile])
            for field in ("canvas", "source_canvas", "expected_canvas"):
                canvas = container.get(field)
                if not isinstance(canvas, dict):
                    continue
                width = canvas.get("width_px")
                height = canvas.get("height_px")
                if type(width) is int and type(height) is int and width > 0 and height > 0:
                    values.append((width, height))
    distinct = set(values)
    if len(distinct) > 1:
        raise ValueError(f"page declares conflicting canvases: {sorted(distinct)}")
    return values[0] if values else None


def _page_number(page: dict[str, Any], index: int) -> int:
    raw = page.get("page", index)
    try:
        number = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid page number at index {index}: {raw!r}") from exc
    if number < 1:
        raise ValueError(f"page number must be positive: {number}")
    return number


def _pages(document: dict[str, Any], name: str) -> list[dict[str, Any]]:
    pages = document.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"{name} must contain a non-empty pages list")
    if not all(isinstance(page, dict) for page in pages):
        raise ValueError(f"{name}.pages must contain objects")
    return pages


def _plan(book_dir: Path) -> dict[str, Any]:
    book_dir = book_dir.resolve()
    content_dir, _layout = _resolve_content_layout(book_dir)
    story_path = next(
        (candidate for candidate in (content_dir / "story.md", book_dir / "story.md") if candidate.is_file()),
        content_dir / "story.md",
    )
    if not story_path.exists():
        raise ValueError("complete story is required before image generation: story.md")
    story_text = story_path.read_text(encoding="utf-8")
    if not story_text.strip():
        raise ValueError("complete story is required before image generation: story.md")
    story_sha256 = _file_hash(story_path)

    manifest = _read_json(content_dir / "page-manifest.json")
    storyboard = _read_json(content_dir / "storyboard.json")
    layout = _read_json(content_dir / "layout.json")
    manifest_pages = _pages(manifest, "page-manifest.json")
    storyboard_pages = _pages(storyboard, "storyboard.json")
    layout_pages = _pages(layout, "layout.json")
    if not (len(manifest_pages) == len(storyboard_pages) == len(layout_pages)):
        raise ValueError("storyboard, page manifest, and layout must be complete for the same page count")

    manifest_by_page: dict[int, dict[str, Any]] = {}
    storyboard_by_page: dict[int, dict[str, Any]] = {}
    layout_by_page: dict[int, dict[str, Any]] = {}
    for index, page in enumerate(manifest_pages, start=1):
        number = _page_number(page, index)
        if number in manifest_by_page:
            raise ValueError(f"duplicate page in page-manifest.json: {number}")
        manifest_by_page[number] = page
    for index, page in enumerate(storyboard_pages, start=1):
        number = _page_number(page, index)
        storyboard_by_page[number] = page
    for index, page in enumerate(layout_pages, start=1):
        number = _page_number(page, index)
        layout_by_page[number] = page
    page_numbers = sorted(manifest_by_page)
    if page_numbers != sorted(storyboard_by_page) or page_numbers != sorted(layout_by_page):
        raise ValueError("storyboard, page manifest, and layout page numbers must match")

    ages = {str(manifest.get("age_band", "")).strip()}
    character_versions: set[str] = set()
    character_paths: set[str] = set()
    style_versions: set[str] = set()
    jobs: list[dict[str, Any]] = []
    for number in page_numbers:
        page = manifest_by_page[number]
        prompt_path_value = page.get("current_prompt_path") or page.get("prompt_path")
        if not isinstance(prompt_path_value, str) or not prompt_path_value.strip():
            raise ValueError(f"page {number} is missing its completed prompt path")
        prompt_path = _resolve_book_path(book_dir, prompt_path_value)
        if prompt_path is None or not prompt_path.is_file():
            raise ValueError(f"page {number} prompt does not exist: {prompt_path_value}")

        character_path_value = page.get("character_reference_path")
        if not isinstance(character_path_value, str) or not character_path_value.strip():
            raise ValueError(f"page {number} is missing character_reference_path")
        character_path = _resolve_book_path(book_dir, character_path_value)
        if character_path is None or not character_path.is_file():
            raise ValueError(f"page {number} character reference does not exist: {character_path_value}")

        production_path_value = page.get("production_reference_path") or character_path_value
        production_path = _resolve_book_path(book_dir, production_path_value)
        if production_path is None or not production_path.is_file():
            raise ValueError(f"page {number} production reference does not exist: {production_path_value}")
        reference_assets = _page_reference_assets(book_dir, page)
        page_task = assemble_page_task(
            page,
            storyboard_page=storyboard_by_page[number],
            project_root=book_dir,
        )

        character_versions.add(str(page.get("characters_version", "")).strip())
        character_paths.add(Path(character_path_value).as_posix())
        layout_page = layout_by_page[number]
        style_value = layout_page.get("style_version") or layout_page.get("layout_style_version")
        nested_layout_design = layout_page.get("layout_design")
        if style_value is None and isinstance(nested_layout_design, dict):
            style_value = nested_layout_design.get("style_version") or nested_layout_design.get("layout_style_version")
        if style_value is not None:
            style_versions.add(str(style_value).strip())
        story_dependency_specs = [
            _story_dependency_value(page),
            _story_dependency_value(storyboard_by_page[number]),
        ]
        story_dependency_scope, story_dependency_fingerprint = _story_dependency_fingerprint(
            story_text,
            story_path,
            book_dir,
            story_dependency_specs,
            story_sha256,
        )
        declared_aspect_ratio = _declared_aspect_ratio(
            page,
            storyboard_by_page[number],
            layout_page,
        )
        expected_canvas = _declared_canvas(
            page,
            storyboard_by_page[number],
            layout_page,
        )
        prompt_hash = _file_hash(prompt_path)
        ref_hash = _file_hash(character_path)
        production_hash = _file_hash(production_path)
        asset_dependency_fingerprint = _asset_dependency_fingerprint(
            page,
            storyboard_page=storyboard_by_page[number],
            layout_page=layout_page,
            prompt_hash=prompt_hash,
            character_hash=ref_hash,
            production_hash=production_hash,
            style_version=str(style_value).strip() if style_value is not None else None,
            declared_aspect_ratio=declared_aspect_ratio,
            reference_assets=reference_assets,
        )
        layout_fingerprint = {
            "source_aspect_ratio": declared_aspect_ratio,
            "expected_canvas": list(expected_canvas) if expected_canvas else None,
            "style_version": style_value,
        }
        base_fingerprint = _canonical_hash(
            {
                "page": number,
                "page_id": page.get("page_id") or f"PAGE-{number:02d}",
                "page_version": page.get("page_version"),
                "image_manifest_page": _image_page_inputs(page),
                "image_storyboard_page": _image_page_inputs(storyboard_by_page[number]),
                "prompt_hash": prompt_hash,
                "character_reference": Path(character_path_value).as_posix(),
                "character_hash": ref_hash,
                "production_reference": Path(production_path_value).as_posix(),
                "production_hash": production_hash,
                "reference_assets": reference_assets,
                "asset_dependency_fingerprint": asset_dependency_fingerprint,
                "story_dependency_scope": story_dependency_scope,
                "story_dependency_fingerprint": story_dependency_fingerprint,
                "layout_fingerprint": layout_fingerprint,
            }
        )
        current_output = page.get("current_image_path")
        output_path = _resolve_output_path(book_dir, current_output)
        if output_path is None:
            output_path = book_dir / "images" / f"page-{number:02d}.png"
        output_relative = _relative_to_book(book_dir, output_path)
        cached = False
        output_sha256 = None
        image_validation = None
        output_error = None
        if output_path.is_file():
            try:
                image_validation = _validate_image_file(
                    output_path,
                    declared_aspect_ratio,
                    expected_canvas,
                )
            except ValueError as exc:
                output_error = str(exc)
            else:
                cached = True
                output_sha256 = _file_hash(output_path)
        dependency_descriptor: Any
        present_dependencies = [dependency for dependency in story_dependency_specs if dependency is not None]
        if not present_dependencies:
            dependency_descriptor = None
        elif len(present_dependencies) == 1 or present_dependencies[0] == present_dependencies[-1]:
            dependency_descriptor = present_dependencies[0]
        else:
            dependency_descriptor = {
                "manifest": story_dependency_specs[0],
                "storyboard": story_dependency_specs[1],
            }
        jobs.append(
            {
                "job_id": f"page-{number:02d}",
                "page": number,
                "page_id": page.get("page_id") or f"PAGE-{number:02d}",
                "page_version": page.get("page_version"),
                "revision": 1,
                "status": "cached" if cached else "pending",
                "attempts": 0,
                "max_attempts": DEFAULT_MAX_ATTEMPTS,
                "request_fingerprint": base_fingerprint,
                "base_request_fingerprint": base_fingerprint,
                "asset_dependency_fingerprint": asset_dependency_fingerprint,
                "prompt_path": Path(prompt_path_value).as_posix(),
                "character_reference_path": Path(character_path_value).as_posix(),
                "production_reference_path": Path(production_path_value).as_posix(),
                "reference_assets": reference_assets,
                "page_task": page_task,
                "continuity_task": page_task["continuity_task"],
                "story_dependency": dependency_descriptor,
                "story_dependency_mode": "page" if story_dependency_scope == "page" else "book",
                "story_dependency_scope": story_dependency_scope,
                "story_dependency_fingerprint": story_dependency_fingerprint,
                "declared_aspect_ratio": declared_aspect_ratio,
                "expected_canvas": list(expected_canvas) if expected_canvas else None,
                "output_path": output_relative,
                "previous_output_path": None,
                "output_sha256": output_sha256,
                "image_validation": image_validation,
                "errors": [],
                "last_error": output_error,
                "elapsed_ms": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
        )

    if len(ages) != 1 or "" in ages:
        raise ValueError("all pages must use one confirmed age band")
    if len(character_versions) != 1 or "" in character_versions:
        raise ValueError("all pages must use one approved character-bible version")
    if len(style_versions) > 1:
        raise ValueError("all pages must use one approved layout/style version")

    plan_fingerprint = _canonical_hash(
        {
            "story_sha256": story_sha256,
            "manifest": manifest,
            "storyboard": storyboard,
            "layout": layout,
            "jobs": [{"page": job["page"], "fingerprint": job["base_request_fingerprint"]} for job in jobs],
        }
    )
    return {
        "book_dir": str(book_dir),
        "title": manifest.get("title"),
        "age_band": manifest.get("age_band"),
        "page_count": len(jobs),
        "plan_fingerprint": plan_fingerprint,
        "story_sha256": story_sha256,
        "character_reference_path": next(iter(character_paths)) if len(character_paths) == 1 else None,
        "character_reference_paths": sorted(character_paths),
        "character_version": next(iter(character_versions)),
        "jobs": jobs,
    }


def _load_queue(queue_path: Path) -> dict[str, Any]:
    state = _read_json(queue_path)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported queue schema: {state.get('schema_version')!r}")
    if not isinstance(state.get("jobs"), list):
        raise ValueError("queue jobs must be a list")
    return state


def _save_queue(queue_path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    _write_atomic(queue_path, state)


def _job(state: dict[str, Any], page: int) -> dict[str, Any]:
    for job in state["jobs"]:
        if int(job["page"]) == int(page):
            return job
    raise ValueError(f"page is not in queue: {page}")


def _append_event(state: dict[str, Any], event: str, page: int | None = None, **fields: Any) -> None:
    record = {"event": event, "at": _now(), **fields}
    if page is not None:
        record["page"] = int(page)
    state.setdefault("events", []).append(record)


def _page_event_fields(job: dict[str, Any]) -> dict[str, Any]:
    """Return stable page metadata shared by queue events."""
    return {
        "page_id": job.get("page_id") or f"PAGE-{int(job['page']):02d}",
        "page_version": job.get("page_version"),
        "revision": int(job.get("revision", 1)),
        "asset_dependency_fingerprint": job.get("asset_dependency_fingerprint"),
    }


def _request_lifecycle(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the optional request ledger, preserving schema-v1 queues."""
    records = state.setdefault("request_lifecycle", [])
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("request_lifecycle must be a list of objects")
    return records


def _request_record(state: dict[str, Any], request_id: str) -> dict[str, Any]:
    request_id = str(request_id).strip()
    if not request_id:
        raise ValueError("request_id must be non-empty")
    for record in _request_lifecycle(state):
        if record.get("request_id") == request_id:
            return record
    raise ValueError(f"request is not in lifecycle ledger: {request_id}")


def _new_request_record(
    job: dict[str, Any],
    *,
    recovery_of_request_id: str | None = None,
    recovery_approval: str | None = None,
) -> dict[str, Any]:
    return {
        "lifecycle_schema_version": REQUEST_LIFECYCLE_SCHEMA_VERSION,
        "request_id": f"request-{uuid.uuid4().hex}",
        "page": int(job["page"]),
        "page_id": job.get("page_id") or f"PAGE-{int(job['page']):02d}",
        "page_version": job.get("page_version") or UNKNOWN,
        "revision": int(job.get("revision", 1)),
        "attempt": int(job.get("attempts", 0)),
        "local_started_at": job.get("started_at") or UNKNOWN,
        "submission_observed": False,
        "backend_task_id": UNKNOWN,
        "wrapper_finished_at": None,
        "wrapper_elapsed_ms": UNKNOWN,
        "terminal_state": "running",
        "artifact_path": None,
        "artifact_sha256": None,
        "failure_code": None,
        "model_wait_ms": UNKNOWN,
        "cost": COST_UNKNOWN,
        "recovery_of_request_id": recovery_of_request_id,
        "recovery_approval": recovery_approval,
        "local_timeout_observed": False,
    }


def _append_request_record(
    state: dict[str, Any],
    job: dict[str, Any],
    *,
    recovery_of_request_id: str | None = None,
    recovery_approval: str | None = None,
) -> dict[str, Any]:
    record = _new_request_record(
        job,
        recovery_of_request_id=recovery_of_request_id,
        recovery_approval=recovery_approval,
    )
    _request_lifecycle(state).append(record)
    job["current_request_id"] = record["request_id"]
    job[LIFECYCLE_ENFORCED_FIELD] = True
    return record


def _update_request_record(state: dict[str, Any], request_id: str, event: str, **updates: Any) -> dict[str, Any]:
    record = _request_record(state, request_id)
    next_state = updates.get("terminal_state")
    current_state = record.get("terminal_state")
    if next_state is not None and next_state not in REQUEST_STATES:
        raise ValueError(f"terminal_state must be one of {sorted(REQUEST_STATES)!r}")
    if current_state in {"succeeded", "failed", "pending_unknown"} and next_state not in {None, current_state}:
        raise RuntimeError(f"request {request_id} is already terminal: {current_state}")
    changed = {key: value for key, value in updates.items() if record.get(key) != value}
    if not changed:
        return copy.deepcopy(record)
    record.update(changed)
    _append_event(state, event, record.get("page"), request_id=request_id, changes=copy.deepcopy(changed))
    return copy.deepcopy(record)


def _current_request(state: dict[str, Any], job: dict[str, Any]) -> dict[str, Any] | None:
    request_id = job.get("current_request_id")
    if not request_id:
        return None
    return _request_record(state, request_id)


def _completion_request(state: dict[str, Any], job: dict[str, Any]) -> dict[str, Any] | None:
    """Validate the request boundary for a new lifecycle-tracked completion.

    Jobs created before lifecycle enforcement have no marker and remain
    readable/completeable for schema-v1 compatibility.  Every new claim gets
    the marker in ``_append_request_record``; a missing or inconsistent record
    therefore cannot silently fall back to the legacy path.
    """
    if job.get(LIFECYCLE_ENFORCED_FIELD) is not True:
        return None
    request_id = job.get("current_request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("REQUEST_LIFECYCLE_RECORD_MISSING")
    try:
        request = _request_record(state, request_id)
    except ValueError as exc:
        raise ValueError("REQUEST_LIFECYCLE_RECORD_MISSING") from exc
    expected_page_id = job.get("page_id") or f"PAGE-{int(job['page']):02d}"
    expected_page_version = job.get("page_version") or UNKNOWN
    if (
        request.get("request_id") != request_id
        or request.get("page") != int(job["page"])
        or request.get("page_id") != expected_page_id
        or request.get("page_version") != expected_page_version
        or request.get("revision") != int(job.get("revision", 1))
        or request.get("attempt") != int(job.get("attempts", 0))
    ):
        raise ValueError("REQUEST_LIFECYCLE_IDENTITY_MISMATCH")
    if request.get("terminal_state") != "running":
        raise RuntimeError("REQUEST_LIFECYCLE_STATE_INVALID")
    if request.get("submission_observed") is not True:
        raise ValueError("REQUEST_SUBMISSION_NOT_OBSERVED")
    try:
        validate_request_lifecycle_record(
            request,
            expected_page_id=expected_page_id,
            expected_page_version=expected_page_version,
        )
    except ValueError as exc:
        raise ValueError("REQUEST_LIFECYCLE_RECORD_INVALID") from exc
    return request


def validate_request_lifecycle_record(
    record: dict[str, Any],
    *,
    expected_page_id: str | None = None,
    expected_page_version: str | None = None,
    book_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one lifecycle record without inventing server or billing data."""
    if not isinstance(record, dict):
        raise ValueError("request lifecycle record must be an object")
    for field in ("request_id", "page_id", "page_version", "backend_task_id", "terminal_state", "cost"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if expected_page_id is not None and record["page_id"] != expected_page_id:
        raise ValueError("page_id does not match expected page")
    if expected_page_version is not None and record["page_version"] != expected_page_version:
        raise ValueError("page_version does not match expected page version")
    if type(record.get("revision")) is not int or record["revision"] < 1:
        raise ValueError("revision must be a positive integer")
    if type(record.get("attempt")) is not int or record["attempt"] < 1:
        raise ValueError("attempt must be a positive integer")
    if record["terminal_state"] not in REQUEST_STATES:
        raise ValueError(f"terminal_state must be one of {sorted(REQUEST_STATES)!r}")
    if record.get("wrapper_elapsed_ms") != UNKNOWN and (type(record.get("wrapper_elapsed_ms")) is not int or record["wrapper_elapsed_ms"] < 0):
        raise ValueError("wrapper_elapsed_ms must be a non-negative integer or 'unknown'")
    if record.get("model_wait_ms") != UNKNOWN and (type(record.get("model_wait_ms")) is not int or record["model_wait_ms"] < 0):
        raise ValueError("model_wait_ms must be a non-negative integer or 'unknown'")
    artifact_path = record.get("artifact_path")
    artifact_hash = record.get("artifact_sha256")
    if artifact_path in (None, UNKNOWN):
        if artifact_hash not in (None, UNKNOWN):
            raise ValueError("artifact_sha256 requires an artifact")
    else:
        if not isinstance(artifact_path, str) or not isinstance(artifact_hash, str) or len(artifact_hash) != 64:
            raise ValueError("artifact path and SHA-256 are required together")
        if book_dir is None:
            raise ValueError("book_dir is required to validate an artifact")
        root = Path(book_dir).resolve()
        artifact = (root / artifact_path).resolve()
        try:
            artifact.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact must remain inside book directory") from exc
        if not artifact.is_file():
            raise ValueError("artifact file does not exist")
        if _file_hash(artifact) != artifact_hash:
            raise ValueError("artifact SHA-256 does not match file")
    return copy.deepcopy(record)


def _book_path_from_queue(state: dict[str, Any], value: str | Path) -> Path:
    return Path(state["book_dir"]) / value if not Path(value).is_absolute() else Path(value)


def init_queue(
    book_dir: str | Path,
    queue_path: str | Path,
    *,
    max_in_flight: int = DEFAULT_MAX_IN_FLIGHT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any]:
    if max_in_flight < 1 or max_in_flight > 3:
        raise ValueError("max_in_flight must be between 1 and 3")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    book_dir = Path(book_dir).resolve()
    queue_path = Path(queue_path).resolve()
    planned = _plan(book_dir)
    with _queue_mutation_lock(queue_path):
        existing: dict[str, Any] | None = None
        if queue_path.exists():
            existing = _load_queue(queue_path)
            if Path(existing["book_dir"]).resolve() != book_dir:
                raise ValueError("existing queue belongs to a different book directory")

        old_by_page = {int(job["page"]): job for job in existing.get("jobs", [])} if existing else {}
        jobs = []
        for fresh in planned["jobs"]:
            old = old_by_page.get(int(fresh["page"]))
            if old and old.get("base_request_fingerprint") == fresh["base_request_fingerprint"]:
                preserved = copy.deepcopy(old)
                preserved["max_attempts"] = max_attempts
                for key in (
                    "page_id",
                    "page_version",
                    "story_dependency",
                    "story_dependency_mode",
                    "story_dependency_scope",
                    "story_dependency_fingerprint",
                    "declared_aspect_ratio",
                    "expected_canvas",
                    "asset_dependency_fingerprint",
                    "reference_assets",
                ):
                    preserved[key] = fresh.get(key)
                output = _book_path_from_queue({"book_dir": str(book_dir)}, preserved.get("output_path", ""))
                if preserved.get("status") in DONE_STATUSES:
                    try:
                        expected_canvas = fresh.get("expected_canvas")
                        expected_canvas_tuple = (
                            tuple(expected_canvas)
                            if isinstance(expected_canvas, list) and len(expected_canvas) == 2
                            else None
                        )
                        image_validation = _validate_image_file(
                            output,
                            fresh.get("declared_aspect_ratio"),
                            expected_canvas_tuple,
                        )
                    except ValueError as exc:
                        preserved["status"] = "pending"
                        preserved["output_sha256"] = None
                        preserved["image_validation"] = None
                        preserved["last_error"] = str(exc)
                    else:
                        if output.is_file() and preserved.get("output_sha256") == _file_hash(output):
                            preserved["status"] = "cached"
                            preserved["image_validation"] = image_validation
                            preserved["updated_at"] = _now()
                            preserved["last_error"] = None
                            jobs.append(preserved)
                            continue
                        preserved["status"] = "pending"
                        preserved["output_sha256"] = None
                        preserved["last_error"] = "previous output is missing or has changed"
                if preserved.get("status") == "running":
                    preserved["status"] = "retryable" if int(preserved.get("attempts", 0)) < max_attempts else "failed"
                jobs.append(preserved)
                continue
            fresh["max_attempts"] = max_attempts
            if old:
                # A changed request must never be treated as a cache hit merely
                # because it points at the previous page's output path.
                fresh["status"] = "pending"
                fresh["output_sha256"] = None
                fresh["last_error"] = "request fingerprint changed; previous output is not reusable"
            jobs.append(fresh)

        state = {
            "schema_version": SCHEMA_VERSION,
            "coordination_mode": COORDINATION_MODE,
            "queue_id": existing.get("queue_id") if existing else f"queue-{int(time.time() * 1000)}",
            "book_dir": str(book_dir),
            "title": planned["title"],
            "age_band": planned["age_band"],
            "page_count": planned["page_count"],
            "plan_fingerprint": planned["plan_fingerprint"],
            "story_sha256": planned["story_sha256"],
        "character_reference_path": planned["character_reference_path"],
        "character_reference_paths": planned["character_reference_paths"],
            "character_version": planned["character_version"],
            "max_in_flight": max_in_flight,
            "max_attempts": max_attempts,
            "jobs": jobs,
            "events": copy.deepcopy(existing.get("events", [])) if existing else [],
            "request_lifecycle": copy.deepcopy(existing.get("request_lifecycle", [])) if existing else [],
            "recovery_authorizations": copy.deepcopy(existing.get("recovery_authorizations", [])) if existing else [],
            "created_at": existing.get("created_at") if existing else _now(),
            "updated_at": _now(),
        }
        _append_event(
            state,
            "initialized",
            plan_fingerprint=planned["plan_fingerprint"],
            reused=bool(existing),
            page_records=[
                {
                    **_page_event_fields(job),
                    "status": job.get("status"),
                }
                for job in jobs
            ],
        )
        _write_atomic(queue_path, state)
        return state


def _claim_job_state(
    state: dict[str, Any],
    job: dict[str, Any],
    *,
    recovery_of_request_id: str | None = None,
    recovery_approval: str | None = None,
    emit_claim_event: bool = True,
) -> dict[str, Any]:
    if job["status"] in DONE_STATUSES:
        raise RuntimeError(f"page {job['page']} is already complete; reset it explicitly to regenerate")
    current = _current_request(state, job)
    if current and current.get("terminal_state") in {"timed_out", "pending_unknown"} and recovery_of_request_id is None:
        raise RuntimeError(f"page {job['page']} has an unresolved unknown request; recovery authorization is required")
    if recovery_of_request_id is not None:
        if not recovery_approval:
            raise PermissionError("recovery authorization is required")
        original = _request_record(state, recovery_of_request_id)
        if int(original.get("page", -1)) != int(job["page"]):
            raise ValueError("recovery request belongs to a different page")
    if job["status"] == "failed" and int(job.get("attempts", 0)) >= int(job.get("max_attempts", state["max_attempts"])):
        raise RuntimeError(f"page {job['page']} exhausted its retry budget")
    job["status"] = "running"
    job["attempts"] = int(job.get("attempts", 0)) + 1
    job["started_at"] = _now()
    job["updated_at"] = _now()
    job["last_error"] = None
    if recovery_of_request_id is not None:
        job["recovery_of_request_id"] = recovery_of_request_id
        job["recovery_approval"] = recovery_approval
    record = _append_request_record(
        state,
        job,
        recovery_of_request_id=recovery_of_request_id,
        recovery_approval=recovery_approval,
    )
    if emit_claim_event:
        _append_event(
            state,
            "claimed",
            int(job["page"]),
            attempt=job["attempts"],
            request_id=record["request_id"],
            **_page_event_fields(job),
        )
    return copy.deepcopy(job)


def claim_job(queue_path: str | Path, page: int) -> dict[str, Any]:
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        job = _job(state, page)
        running = sum(1 for item in state["jobs"] if item["status"] in ACTIVE_STATUSES)
        if running >= int(state["max_in_flight"]):
            raise RuntimeError("max_in_flight reached; complete or fail a running page first")
        result = _claim_job_state(state, job)
        _save_queue(queue_path, state)
        return result


def claim_batch(queue_path: str | Path, pages: list[int]) -> list[dict[str, Any]]:
    """Atomically claim a bounded page group for one host coordinator.

    The batch limit controls queue bookkeeping only; it does not claim that the
    host image tool can execute multiple image requests in parallel.
    """
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        normalized = [int(page) for page in pages]
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("claim batch requires one or more distinct page numbers")
        jobs = [_job(state, page) for page in normalized]
        running = sum(1 for item in state["jobs"] if item["status"] in ACTIVE_STATUSES)
        capacity = int(state["max_in_flight"]) - running
        if len(jobs) > capacity:
            raise RuntimeError(f"batch has {len(jobs)} pages but only {max(capacity, 0)} in-flight slots are available")
        for job in jobs:
            if job["status"] in DONE_STATUSES:
                raise RuntimeError(f"page {job['page']} is already complete; reset it explicitly to regenerate")
            if job["status"] == "failed" and int(job.get("attempts", 0)) >= int(job.get("max_attempts", state["max_attempts"])):
                raise RuntimeError(f"page {job['page']} exhausted its retry budget")
        for job in jobs:
            if _current_request(state, job) and _current_request(state, job).get("terminal_state") in {"timed_out", "pending_unknown"}:
                raise RuntimeError(f"page {job['page']} has an unresolved unknown request; recovery authorization is required")
        claimed_jobs = [_claim_job_state(state, job, emit_claim_event=False) for job in jobs]
        _append_event(
            state,
            "batch_claimed",
            pages=normalized,
            attempts=[job["attempts"] for job in claimed_jobs],
            page_records=[
                {**_page_event_fields(job), "attempt": job["attempts"], "request_id": job.get("current_request_id")}
                for job in claimed_jobs
            ],
        )
        _save_queue(queue_path, state)
        return copy.deepcopy(claimed_jobs)


def complete_job(
    queue_path: str | Path,
    page: int,
    output_path: str | Path,
    *,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        job = _job(state, page)
        if job["status"] != "running":
            raise RuntimeError(f"page {page} must be running before completion")
        request = _completion_request(state, job)
        output = Path(output_path)
        if not output.is_absolute():
            output = Path(state["book_dir"]) / output
        output = output.resolve()
        relative = _relative_to_book(Path(state["book_dir"]), output)
        if not output.is_file():
            raise ValueError(f"completed image does not exist: {output}")
        expected_canvas = job.get("expected_canvas")
        expected_canvas_tuple = (
            tuple(expected_canvas)
            if isinstance(expected_canvas, list) and len(expected_canvas) == 2
            else None
        )
        image_validation = _validate_image_file(
            output,
            job.get("declared_aspect_ratio"),
            expected_canvas_tuple,
        )
        job.update(
            {
                "status": "completed",
                "output_path": relative,
                "output_sha256": _file_hash(output),
                "image_validation": image_validation,
                "elapsed_ms": elapsed_ms,
                "finished_at": _now(),
                "updated_at": _now(),
                "last_error": None,
            }
        )
        if request is not None:
            _update_request_record(
                state,
                request["request_id"],
                "request_completed",
                terminal_state="succeeded",
                wrapper_finished_at=job["finished_at"],
                wrapper_elapsed_ms=elapsed_ms if type(elapsed_ms) is int and elapsed_ms >= 0 else UNKNOWN,
                artifact_path=relative,
                artifact_sha256=job["output_sha256"],
            )
        _append_event(
            state,
            "completed",
            page,
            elapsed_ms=elapsed_ms,
            output_path=relative,
            request_id=job.get("current_request_id"),
            **_page_event_fields(job),
        )
        _save_queue(queue_path, state)
        return copy.deepcopy(job)


def fail_job(
    queue_path: str | Path,
    page: int,
    error: str,
    *,
    failure_code: str | None = None,
) -> dict[str, Any]:
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        job = _job(state, page)
        if job["status"] != "running":
            raise RuntimeError(f"page {page} must be running before failure is recorded")
        message = str(error).strip() or "unspecified generation failure"
        code = str(failure_code).strip() if failure_code is not None else "GENERATION_FAILED"
        if not code:
            code = "GENERATION_FAILED"
        job.setdefault("errors", []).append({"at": _now(), "message": message, "failure_code": code})
        job["last_error"] = message
        job["last_failure_code"] = code
        job["status"] = "retryable" if int(job.get("attempts", 0)) < int(job.get("max_attempts", state["max_attempts"])) else "failed"
        job["updated_at"] = _now()
        request = _current_request(state, job)
        if request is not None:
            _update_request_record(
                state,
                request["request_id"],
                "request_failed",
                terminal_state="failed",
                wrapper_finished_at=_now(),
                wrapper_elapsed_ms=UNKNOWN,
                failure_code=code,
            )
        _append_event(
            state,
            "failed",
            page,
            retryable=job["status"] == "retryable",
            message=message,
            failure_code=code,
            request_id=job.get("current_request_id"),
            **_page_event_fields(job),
        )
        _save_queue(queue_path, state)
        return copy.deepcopy(job)


def mark_request_submitted(
    queue_path: str | Path,
    request_id: str,
    *,
    backend_task_id: str | None = None,
) -> dict[str, Any]:
    """Record observed local submission without inventing a backend task ID."""
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        record = _request_record(state, request_id)
        backend = str(backend_task_id).strip() if backend_task_id is not None else UNKNOWN
        if not backend:
            backend = UNKNOWN
        if record.get("submission_observed") is True:
            current_backend = record.get("backend_task_id", UNKNOWN)
            if current_backend not in {UNKNOWN, backend} and backend != UNKNOWN:
                raise ValueError("backend_task_id conflicts with the existing submission record")
            if current_backend == backend or backend == UNKNOWN:
                return copy.deepcopy(record)
        result = _update_request_record(
            state,
            request_id,
            "request_submitted",
            submission_observed=True,
            backend_task_id=backend,
        )
        _save_queue(queue_path, state)
        return result


def mark_request_timeout(
    queue_path: str | Path,
    request_id: str,
    *,
    wrapper_elapsed_ms: int | None = None,
    failure_code: str = "LOCAL_TIMEOUT",
) -> dict[str, Any]:
    """Record a local wrapper timeout; this is not server-side failure evidence."""
    if wrapper_elapsed_ms is not None and (type(wrapper_elapsed_ms) is not int or wrapper_elapsed_ms < 0):
        raise ValueError("wrapper_elapsed_ms must be a non-negative integer or None")
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        record = _request_record(state, request_id)
        if record.get("terminal_state") in {"succeeded", "failed", "pending_unknown"}:
            raise RuntimeError(f"request {request_id} is already terminal: {record.get('terminal_state')}")
        job = _job(state, int(record["page"]))
        job["status"] = "failed"  # old queue consumers remain able to read the page state
        job["last_error"] = "local wrapper timeout; backend state is unknown"
        job["last_failure_code"] = failure_code
        job["updated_at"] = _now()
        result = _update_request_record(
            state,
            request_id,
            "request_timed_out",
            terminal_state="timed_out",
            wrapper_finished_at=_now(),
            wrapper_elapsed_ms=wrapper_elapsed_ms if wrapper_elapsed_ms is not None else UNKNOWN,
            failure_code=str(failure_code).strip() or "LOCAL_TIMEOUT",
            local_timeout_observed=True,
            backend_task_id=record.get("backend_task_id", UNKNOWN),
        )
        _save_queue(queue_path, state)
        return result


def mark_request_pending_unknown(
    queue_path: str | Path,
    request_id: str,
    *,
    reason: str = "no terminal response or local artifact",
) -> dict[str, Any]:
    """Keep an unresolved request explicit and block ordinary retry claims."""
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        record = _request_record(state, request_id)
        if record.get("terminal_state") == "succeeded":
            raise RuntimeError(f"request {request_id} already succeeded")
        job = _job(state, int(record["page"]))
        job["status"] = "failed"
        job["last_error"] = str(reason).strip() or "request state is unknown"
        job["last_failure_code"] = "PENDING_UNKNOWN"
        job["updated_at"] = _now()
        result = _update_request_record(
            state,
            request_id,
            "request_pending_unknown",
            terminal_state="pending_unknown",
            failure_code=record.get("failure_code") or "PENDING_UNKNOWN",
            backend_task_id=record.get("backend_task_id", UNKNOWN),
            model_wait_ms=UNKNOWN,
            cost=COST_UNKNOWN,
        )
        _save_queue(queue_path, state)
        return result


def authorize_page_recovery(
    queue_path: str | Path,
    page: int,
    original_request_id: str,
    *,
    approval: str,
    max_calls: int = 1,
) -> dict[str, Any]:
    """Append one explicit user authorization for one page recovery call."""
    approval = str(approval).strip()
    if not approval:
        raise ValueError("recovery approval must be non-empty")
    if max_calls != 1:
        raise ValueError("safe recovery permits exactly one authorized call")
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        job = _job(state, page)
        original = _request_record(state, original_request_id)
        if int(original.get("page", -1)) != int(page):
            raise ValueError("recovery request belongs to a different page")
        if original.get("terminal_state") not in {"failed", "timed_out", "pending_unknown"}:
            raise RuntimeError("only a failed or unknown request can be recovered")
        existing = [
            item
            for item in state.get("recovery_authorizations", [])
            if item.get("page") == int(page)
            and item.get("original_request_id") == original_request_id
            and int(item.get("used_calls", 0)) < int(item.get("max_calls", 1))
        ]
        if existing:
            raise PermissionError("an unused recovery authorization already exists")
        authorization = {
            "authorization_id": f"recovery-auth-{uuid.uuid4().hex}",
            "page": int(page),
            "page_id": job.get("page_id") or f"PAGE-{int(page):02d}",
            "original_request_id": original_request_id,
            "approval": approval,
            "approved_at": _now(),
            "max_calls": 1,
            "used_calls": 0,
        }
        state.setdefault("recovery_authorizations", []).append(authorization)
        _append_event(state, "recovery_authorized", **authorization)
        _save_queue(queue_path, state)
        return copy.deepcopy(authorization)


def _reset_job_state(state: dict[str, Any], job: dict[str, Any], reason: str) -> None:
    old_output = job.get("output_path")
    if old_output and _book_path_from_queue(state, old_output).is_file():
        job["previous_output_path"] = old_output
    job["previous_request_id"] = job.get("current_request_id")
    job["revision"] = int(job.get("revision", 1)) + 1
    original = Path(job.get("output_path", f"images/page-{int(job['page']):02d}.png"))
    stem = original.stem
    suffix = original.suffix or ".png"
    job["output_path"] = (original.parent / f"{stem}-r{job['revision']}{suffix}").as_posix()
    job["request_fingerprint"] = _canonical_hash(
        {"base": job["base_request_fingerprint"], "revision": job["revision"], "reason": str(reason)}
    )
    job["status"] = "pending"
    job["attempts"] = 0
    job["errors"] = []
    job["last_error"] = None
    job["output_sha256"] = None
    job["elapsed_ms"] = None
    job.pop("current_request_id", None)
    for field in ("image_validation", "started_at", "finished_at"):
        job.pop(field, None)
    job["updated_at"] = _now()
    _append_event(state, "page_reset", int(job["page"]), reason=str(reason), **_page_event_fields(job))


def claim_page_recovery(queue_path: str | Path, page: int, original_request_id: str) -> dict[str, Any]:
    """Consume one authorization and claim a new revision without auto-retry."""
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        job = _job(state, page)
        authorization = next(
            (
                item
                for item in state.get("recovery_authorizations", [])
                if item.get("page") == int(page)
                and item.get("original_request_id") == original_request_id
            ),
            None,
        )
        if authorization is None:
            raise PermissionError("recovery authorization is required")
        if int(authorization.get("used_calls", 0)) >= int(authorization.get("max_calls", 1)):
            raise PermissionError("recovery authorization has already been used")
        if job["status"] in ACTIVE_STATUSES or job["status"] in DONE_STATUSES:
            raise RuntimeError("page must be idle before recovery")
        _reset_job_state(state, job, "authorized page recovery")
        claimed = _claim_job_state(
            state,
            job,
            recovery_of_request_id=original_request_id,
            recovery_approval=authorization["approval"],
        )
        authorization["used_calls"] = int(authorization.get("used_calls", 0)) + 1
        authorization["used_at"] = _now()
        authorization["recovery_request_id"] = claimed["current_request_id"]
        _append_event(
            state,
            "recovery_claimed",
            page,
            request_id=claimed["current_request_id"],
            recovery_of_request_id=original_request_id,
            recovery_approval=authorization["approval"],
        )
        _save_queue(queue_path, state)
        return claimed


def resume_queue(queue_path: str | Path) -> dict[str, Any]:
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        changed = []
        for job in state["jobs"]:
            if job["status"] in ACTIVE_STATUSES:
                request = None
                if job.get(LIFECYCLE_ENFORCED_FIELD) is True:
                    try:
                        request = _current_request(state, job)
                    except ValueError:
                        job["status"] = "failed"
                        job["last_error"] = "lifecycle record is missing during resume"
                        job["last_failure_code"] = "REQUEST_LIFECYCLE_RECORD_MISSING"
                        job["updated_at"] = _now()
                        changed.append(int(job["page"]))
                        continue
                if request is not None and request.get("submission_observed") is True:
                    job["status"] = "failed"
                    job["last_error"] = "resume interrupted after observed submission; backend state is unknown"
                    job["last_failure_code"] = "PENDING_UNKNOWN"
                    _update_request_record(
                        state,
                        request["request_id"],
                        "request_pending_unknown",
                        terminal_state="pending_unknown",
                        failure_code="PENDING_UNKNOWN",
                        backend_task_id=request.get("backend_task_id", UNKNOWN),
                        model_wait_ms=UNKNOWN,
                        cost=COST_UNKNOWN,
                    )
                else:
                    job["status"] = "retryable" if int(job.get("attempts", 0)) < int(job.get("max_attempts", state["max_attempts"])) else "failed"
                    job["last_error"] = "local interruption before observed submission"
                    job["last_failure_code"] = "LOCAL_INTERRUPTION_BEFORE_SUBMISSION"
                    if request is not None:
                        _update_request_record(
                            state,
                            request["request_id"],
                            "request_failed",
                            terminal_state="failed",
                            failure_code="LOCAL_INTERRUPTION_BEFORE_SUBMISSION",
                            wrapper_finished_at=_now(),
                            wrapper_elapsed_ms=UNKNOWN,
                        )
                job["updated_at"] = _now()
                changed.append(int(job["page"]))
        _append_event(
            state,
            "resumed",
            pages=changed,
            page_records=[
                {**_page_event_fields(job), "status": job.get("status")}
                for job in state["jobs"]
                if int(job["page"]) in changed
            ],
        )
        _save_queue(queue_path, state)
        return state


def reset_page(queue_path: str | Path, page: int, reason: str) -> dict[str, Any]:
    queue_path = Path(queue_path).resolve()
    with _queue_mutation_lock(queue_path):
        state = _load_queue(queue_path)
        job = _job(state, page)
        if job["status"] == "running":
            raise RuntimeError("cannot reset a running page; resume or fail it first")
        if job.get(LIFECYCLE_ENFORCED_FIELD) is True:
            try:
                request = _current_request(state, job)
            except ValueError as exc:
                raise ValueError("REQUEST_LIFECYCLE_RECORD_MISSING") from exc
            if request.get("terminal_state") in {"timed_out", "pending_unknown"}:
                raise PermissionError("recovery authorization is required for an unknown request")
        _reset_job_state(state, job, reason)
        _save_queue(queue_path, state)
        return state


def status(queue_path: str | Path) -> dict[str, Any]:
    state = _load_queue(Path(queue_path).resolve())
    counts = {key: 0 for key in ("pending", "running", "retryable", "failed", "completed", "cached")}
    attempts = 0
    elapsed_ms = 0
    for job in state["jobs"]:
        status_name = str(job.get("status"))
        counts[status_name] = counts.get(status_name, 0) + 1
        attempts += int(job.get("attempts", 0))
        if isinstance(job.get("elapsed_ms"), int):
            elapsed_ms += int(job["elapsed_ms"])
    failures = sum(1 for event in state.get("events", []) if event.get("event") == "failed")
    return {
        "queue_id": state["queue_id"],
        "coordination_mode": state.get("coordination_mode", COORDINATION_MODE),
        "book_dir": state["book_dir"],
        "page_count": state["page_count"],
        "max_in_flight": state["max_in_flight"],
        "counts": counts,
        "attempts": attempts,
        "failure_events": failures,
        "retry_events": sum(1 for event in state.get("events", []) if event.get("event") == "failed" and event.get("retryable")),
        "recorded_image_elapsed_ms": elapsed_ms,
        "updated_at": state["updated_at"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="validate the complete plan and create/reuse one page job per page")
    init.add_argument("book_dir", type=Path)
    init.add_argument("queue_json", type=Path)
    init.add_argument("--max-in-flight", type=int, default=DEFAULT_MAX_IN_FLIGHT)
    init.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("queue_json", type=Path)
    claim = subparsers.add_parser("claim")
    claim.add_argument("queue_json", type=Path)
    claim.add_argument("--page", type=int, required=True)
    batch = subparsers.add_parser("claim-batch", help="atomically claim a bounded group of pages")
    batch.add_argument("queue_json", type=Path)
    batch.add_argument("--pages", type=int, nargs="+", required=True)
    complete = subparsers.add_parser("complete")
    complete.add_argument("queue_json", type=Path)
    complete.add_argument("--page", type=int, required=True)
    complete.add_argument("--output", type=Path, required=True)
    complete.add_argument("--elapsed-ms", type=int)
    fail = subparsers.add_parser("fail")
    fail.add_argument("queue_json", type=Path)
    fail.add_argument("--page", type=int, required=True)
    fail.add_argument("--error", required=True)
    fail.add_argument("--failure-code")
    resume = subparsers.add_parser("resume")
    resume.add_argument("queue_json", type=Path)
    reset = subparsers.add_parser("reset-page")
    reset.add_argument("queue_json", type=Path)
    reset.add_argument("--page", type=int, required=True)
    reset.add_argument("--reason", required=True)
    submitted = subparsers.add_parser("mark-submitted")
    submitted.add_argument("queue_json", type=Path)
    submitted.add_argument("--request-id", required=True)
    submitted.add_argument("--backend-task-id")
    timeout = subparsers.add_parser("timeout-request")
    timeout.add_argument("queue_json", type=Path)
    timeout.add_argument("--request-id", required=True)
    timeout.add_argument("--wrapper-elapsed-ms", type=int)
    timeout.add_argument("--failure-code", default="LOCAL_TIMEOUT")
    pending_unknown = subparsers.add_parser("pending-unknown")
    pending_unknown.add_argument("queue_json", type=Path)
    pending_unknown.add_argument("--request-id", required=True)
    pending_unknown.add_argument("--reason", default="no terminal response or local artifact")
    authorize = subparsers.add_parser("authorize-recovery")
    authorize.add_argument("queue_json", type=Path)
    authorize.add_argument("--page", type=int, required=True)
    authorize.add_argument("--request-id", required=True)
    authorize.add_argument("--approval", required=True)
    recovery = subparsers.add_parser("claim-recovery")
    recovery.add_argument("queue_json", type=Path)
    recovery.add_argument("--page", type=int, required=True)
    recovery.add_argument("--request-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            result = init_queue(args.book_dir, args.queue_json, max_in_flight=args.max_in_flight, max_attempts=args.max_attempts)
        elif args.command == "status":
            result = status(args.queue_json)
        elif args.command == "claim":
            result = claim_job(args.queue_json, args.page)
        elif args.command == "claim-batch":
            result = claim_batch(args.queue_json, args.pages)
        elif args.command == "complete":
            result = complete_job(args.queue_json, args.page, args.output, elapsed_ms=args.elapsed_ms)
        elif args.command == "fail":
            result = fail_job(args.queue_json, args.page, args.error, failure_code=args.failure_code)
        elif args.command == "resume":
            result = resume_queue(args.queue_json)
        elif args.command == "reset-page":
            result = reset_page(args.queue_json, args.page, args.reason)
        elif args.command == "mark-submitted":
            result = mark_request_submitted(args.queue_json, args.request_id, backend_task_id=args.backend_task_id)
        elif args.command == "timeout-request":
            result = mark_request_timeout(
                args.queue_json,
                args.request_id,
                wrapper_elapsed_ms=args.wrapper_elapsed_ms,
                failure_code=args.failure_code,
            )
        elif args.command == "pending-unknown":
            result = mark_request_pending_unknown(args.queue_json, args.request_id, reason=args.reason)
        elif args.command == "authorize-recovery":
            result = authorize_page_recovery(
                args.queue_json,
                args.page,
                args.request_id,
                approval=args.approval,
            )
        elif args.command == "claim-recovery":
            result = claim_page_recovery(args.queue_json, args.page, args.request_id)
        else:  # pragma: no cover
            raise ValueError(f"unsupported command: {args.command}")
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

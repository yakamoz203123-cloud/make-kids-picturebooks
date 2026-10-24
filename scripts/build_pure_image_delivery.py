"""Build one deterministic pure-image delivery package.

This entry point never calls an image model, a social-page renderer, or
PowerPoint.  It consumes an approved storyboard and existing page images.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, UnidentifiedImageError

from production_timing import PhaseRecorder, summarize_phase_events
from project_paths import resolve_book_image_file
from render_contact_sheet import render_contact_sheet


OUTPUT_MODE = "pure-images"
WIDTH = 1080
HEIGHT = 1440
ASPECT_RATIO = "3:4"
SCHEMA_VERSION = 1
CONTRACT_FILES = (
    "storyboard.json",
    "page-manifest.json",
    "page-text.json",
    "layout.json",
    "education-goal.json",
    "asset-binding-plan.json",
)
CONTENT_REQUIRED_FILES = CONTRACT_FILES
STORY_FILE = "story.md"


class DeliveryError(ValueError):
    """A deterministic input or output contract failure."""


@dataclass(frozen=True)
class DeliveryContract:
    """Resolved, read-only inputs consumed by the pure-image builder."""

    content_dir: Path
    layout: str
    storyboard: dict[str, Any]
    pages: list[dict[str, Any]]
    age_band: str
    business_book_id: str
    input_paths: dict[str, Path]
    input_hashes: dict[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _project_root(value: str | Path) -> Path:
    path = Path(value).resolve()
    if path.is_file():
        if path.name != "project.json":
            raise DeliveryError("PROJECT_PATH_INVALID")
        return path.parent
    if not path.is_dir() or not (path / "project.json").is_file():
        raise DeliveryError("PROJECT_PATH_INVALID")
    return path


def _read_json(path: Path, error_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(error_code) from exc
    if not isinstance(value, dict):
        raise DeliveryError(error_code)
    return value


def _safe_component(value: str, error_code: str) -> str:
    text = str(value).strip()
    if not text or text in {".", ".."} or any(separator in text for separator in ("/", "\\", ":")):
        raise DeliveryError(error_code)
    return text


def _storyboard_metadata(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("book_id")
    return str(value).strip() if value is not None and str(value).strip() else None


def _book_key(root: Path, requested_book_id: str) -> str:
    requested = _safe_component(requested_book_id, "BOOK_ID_INVALID")
    books_dir = root / "books"
    exact = books_dir / requested
    if exact.is_dir():
        return requested

    matches: set[str] = set()
    project_data = _read_json(root / "project.json", "PROJECT_METADATA_INVALID")
    entries = project_data.get("books")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            identifiers = {
                str(entry.get(key)).strip()
                for key in ("id", "book_id", "business_id", "full_id")
                if entry.get(key) is not None and str(entry.get(key)).strip()
            }
            if requested in identifiers:
                candidate = str(entry.get("id") or entry.get("book_id") or "").strip()
                if candidate and (books_dir / candidate).is_dir():
                    matches.add(candidate)

    if books_dir.is_dir():
        for candidate in sorted(path for path in books_dir.iterdir() if path.is_dir()):
            for version_dir in sorted(path for path in candidate.iterdir() if path.is_dir()):
                for storyboard_path in (version_dir / "storyboard.json", version_dir / "content" / "storyboard.json"):
                    if storyboard_path.is_file() and _storyboard_metadata(storyboard_path) == requested:
                        matches.add(candidate.name)
                        break
                if candidate.name in matches:
                    break

    if len(matches) == 1:
        return next(iter(matches))
    if len(matches) > 1:
        raise DeliveryError("BOOK_ID_AMBIGUOUS")
    raise DeliveryError("BOOK_ID_NOT_FOUND")


def _book_dir(root: Path, book_id: str, version: str | None) -> Path:
    base = root / "books" / _book_key(root, book_id)
    if version:
        result = base / _safe_component(version, "BOOK_VERSION_INVALID")
        if not result.is_dir():
            raise DeliveryError("BOOK_VERSION_NOT_FOUND")
        return result
    candidates = sorted(path for path in base.iterdir() if path.is_dir()) if base.is_dir() else []
    if len(candidates) != 1:
        raise DeliveryError("BOOK_VERSION_REQUIRED")
    return candidates[0]


def _resolve_content_layout(book_dir: Path) -> tuple[Path, str]:
    """Resolve one unambiguous version-root or ``content`` input layout."""

    root_files = {name: book_dir / name for name in CONTRACT_FILES}
    content_dir = book_dir / "content"
    content_files = {name: content_dir / name for name in CONTRACT_FILES}
    root_present = {name for name, path in root_files.items() if path.is_file()}
    content_present = {name for name, path in content_files.items() if path.is_file()}

    if root_present and content_present:
        conflicts = [
            name
            for name in sorted(root_present & content_present)
            if _sha256(root_files[name]) != _sha256(content_files[name])
        ]
        if conflicts:
            raise DeliveryError(f"CONTENT_LAYOUT_CONFLICT:{','.join(conflicts)}")
        if "storyboard.json" not in content_present:
            raise DeliveryError("CONTENT_LAYOUT_CONFLICT")
        return content_dir, "content"
    if content_present:
        return content_dir, "content"
    return book_dir, "version-root"


def _read_storyboard_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.is_file():
        raise DeliveryError(f"STORYBOARD_MISSING:{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeliveryError("STORYBOARD_INVALID") from exc
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list) or not pages:
        raise DeliveryError("STORYBOARD_PAGES_MISSING")
    story_pages: list[dict[str, Any]] = []
    seen: set[int] = set()
    for page in pages:
        if not isinstance(page, dict):
            raise DeliveryError("STORYBOARD_PAGE_INVALID")
        try:
            number = int(page["page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DeliveryError("PAGE_NUMBER_INVALID") from exc
        if number in seen:
            raise DeliveryError("DUPLICATE_PAGE_NUMBER")
        seen.add(number)
        kind = str(page.get("kind", "story")).strip().lower()
        if kind == "cover":
            continue
        text = page.get("text")
        if not isinstance(text, str) or not text.strip():
            raise DeliveryError(f"MISSING_PAGE_TEXT:{number}")
        story_pages.append(page)
    if not story_pages:
        raise DeliveryError("NO_STORY_PAGES")
    return data, story_pages


def _read_storyboard(book_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    content_dir, _ = _resolve_content_layout(book_dir)
    return _read_storyboard_file(content_dir / "storyboard.json")


def _candidate_images(
    book_dir: Path,
    root: Path,
    page: Mapping[str, Any],
    *,
    content_dir: Path | None = None,
) -> list[Path]:
    content_root = (content_dir or _resolve_content_layout(book_dir)[0]).resolve()
    number = int(page["page"])
    declared = page.get("current_image_path")
    if isinstance(declared, str) and declared.strip():
        try:
            candidate = resolve_book_image_file(content_root, declared)
        except ValueError as exc:
            raise DeliveryError("IMAGE_PATH_ESCAPES_BOOK") from exc
        return [candidate]

    stem = f"page-{number:02d}"
    candidates: list[Path] = []
    for directory in (
        content_root / "images" / "pages",
        content_root / "illustrations",
        root / "deliverables" / "images-1080x1440",
    ):
        if not directory.is_dir():
            continue
        exact = [directory / f"{stem}{suffix}" for suffix in (".png", ".jpg", ".jpeg")]
        exact = [path for path in exact if path.is_file()]
        if exact:
            return exact
        candidates.extend(
            sorted(
                path
                for path in directory.glob(f"{stem}-*")
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
            )
        )
    return candidates


def _source_image(
    root: Path,
    book_dir: Path,
    page: Mapping[str, Any],
    *,
    content_dir: Path | None = None,
) -> Path:
    candidates = _candidate_images(book_dir, root, page, content_dir=content_dir)
    if not candidates:
        raise DeliveryError(f"MISSING_PAGE_IMAGE:{int(page['page'])}")
    if len(candidates) == 1 and not candidates[0].is_file():
        raise DeliveryError(f"MISSING_PAGE_IMAGE:{int(page['page'])}")
    if len(candidates) > 1:
        version = str(page.get("page_version", "")).strip()
        preferred = [path for path in candidates if version and version in path.stem]
        if len(preferred) == 1:
            return preferred[0]
        raise DeliveryError(f"AMBIGUOUS_PAGE_IMAGE:{int(page['page'])}")
    return candidates[0]


def _page_number_map(value: Any, name: str) -> dict[int, dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("pages"), list):
        raise DeliveryError(f"{name}_PAGES_MISSING")
    result: dict[int, dict[str, Any]] = {}
    for index, page in enumerate(value["pages"], start=1):
        if not isinstance(page, dict):
            raise DeliveryError(f"{name}_PAGE_INVALID")
        try:
            number = int(page.get("page", index))
        except (TypeError, ValueError) as exc:
            raise DeliveryError(f"{name}_PAGE_NUMBER_INVALID") from exc
        if number in result:
            raise DeliveryError(f"{name}_DUPLICATE_PAGE_NUMBER")
        result[number] = page
    return result


def _metadata_value(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _load_delivery_contract(root: Path, book_dir: Path, requested_book_id: str) -> DeliveryContract:
    content_dir, layout = _resolve_content_layout(book_dir)
    storyboard_path = content_dir / "storyboard.json"
    storyboard, story_pages = _read_storyboard_file(storyboard_path)

    contract_data: dict[str, dict[str, Any]] = {"storyboard.json": storyboard}
    input_paths: dict[str, Path] = {"storyboard.json": storyboard_path}
    for name in CONTRACT_FILES:
        if name == "storyboard.json":
            continue
        path = content_dir / name
        if path.is_file():
            contract_data[name] = _read_json(path, f"{name.upper().replace('.', '_')}_INVALID")
            input_paths[name] = path

    if layout == "content":
        missing = [name for name in CONTENT_REQUIRED_FILES if name not in input_paths]
        if missing:
            raise DeliveryError(f"CONTENT_INPUT_MISSING:{','.join(missing)}")

    story_page_map = _page_number_map(storyboard, "STORYBOARD")
    effective_pages = [dict(page) for page in story_pages]
    manifest = contract_data.get("page-manifest.json")
    if manifest is not None:
        manifest_page_map = _page_number_map(manifest, "PAGE_MANIFEST")
        if set(manifest_page_map) != set(story_page_map):
            raise DeliveryError("CONTRACT_PAGE_NUMBER_CONFLICT")
        for page in effective_pages:
            manifest_page = manifest_page_map[int(page["page"])]
            for field in ("page_id", "page_version", "current_image_path"):
                if field not in page or page.get(field) in (None, ""):
                    if field in manifest_page:
                        page[field] = manifest_page[field]

    for name in ("page-text.json", "layout.json"):
        data = contract_data.get(name)
        if data is None:
            continue
        page_map = _page_number_map(data, name.upper().replace(".", "_"))
        if set(page_map) != set(story_page_map):
            raise DeliveryError("CONTRACT_PAGE_NUMBER_CONFLICT")
        if name == "page-text.json":
            for page in effective_pages:
                declared_text = page.get("text")
                contract_text = page_map[int(page["page"])].get("text")
                if isinstance(contract_text, str) and isinstance(declared_text, str) and contract_text.strip() != declared_text.strip():
                    raise DeliveryError(f"PAGE_TEXT_CONFLICT:{int(page['page'])}")

    metadata_sources = list(contract_data.values())
    business_ids = {
        value
        for data in metadata_sources
        for value in [_metadata_value(data, "book_id", "business_id", "full_id")]
        if value
    }
    if len(business_ids) > 1:
        raise DeliveryError("BOOK_ID_METADATA_CONFLICT")
    business_book_id = next(iter(business_ids), str(requested_book_id).strip())
    requested_id = str(requested_book_id).strip()
    if requested_id != book_dir.parent.name and requested_id != business_book_id:
        raise DeliveryError("BOOK_ID_VERSION_CONFLICT")

    age_values = {
        value
        for data in metadata_sources
        for value in [_metadata_value(data, "age_band", "target_age_band")]
        if value
    }
    if len(age_values) > 1:
        raise DeliveryError("AGE_BAND_CONFLICT")
    age_band = next(iter(age_values), "unknown")

    output_modes = {
        str(data.get("output_mode")).strip()
        for data in metadata_sources
        if data.get("output_mode") is not None and str(data.get("output_mode")).strip()
    }
    if output_modes and output_modes != {OUTPUT_MODE}:
        raise DeliveryError("OUTPUT_MODE_UNSUPPORTED")

    project_path = root / "project.json"
    if project_path.is_file():
        input_paths["project.json"] = project_path
    story_path = content_dir / STORY_FILE
    if story_path.is_file():
        input_paths[STORY_FILE] = story_path
    input_hashes = {name: _sha256(path) for name, path in sorted(input_paths.items())}
    return DeliveryContract(
        content_dir=content_dir,
        layout=layout,
        storyboard=storyboard,
        pages=effective_pages,
        age_band=age_band,
        business_book_id=business_book_id,
        input_paths=input_paths,
        input_hashes=input_hashes,
    )


def _inspect_image(path: Path) -> tuple[int, int, str]:
    if not path.is_file():
        raise DeliveryError(f"MISSING_PAGE_IMAGE:{path.name}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            size = image.size
            image.load()
            if "A" in image.getbands() or "transparency" in image.info:
                alpha = image.convert("RGBA").getchannel("A")
                if alpha.getextrema() != (255, 255):
                    raise DeliveryError(f"INVALID_ALPHA:{path.name}")
    except DeliveryError:
        raise
    except (OSError, UnidentifiedImageError, SyntaxError, ValueError) as exc:
        raise DeliveryError(f"INVALID_IMAGE:{path.name}") from exc
    width, height = size
    if width * 4 != height * 3:
        raise DeliveryError(f"ASPECT_RATIO_MISMATCH:{path.name}")
    if width < WIDTH or height < HEIGHT:
        raise DeliveryError(f"INVALID_DIMENSIONS:{path.name}")
    return width, height, _sha256(path)


def _write_normalized(source: Path, destination: Path) -> tuple[int, int]:
    with Image.open(source) as image:
        image.load()
        if image.size == (WIDTH, HEIGHT) and source.suffix.lower() == ".png" and "A" not in image.getbands() and "transparency" not in image.info:
            shutil.copyfile(source, destination)
            return image.size
        output = image.convert("RGB")
        if output.size != (WIDTH, HEIGHT):
            output = output.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        output.save(destination, format="PNG", optimize=False)
        output.close()
        return (WIDTH, HEIGHT)


def _load_previous_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / "page-text-manifest.json"
    validation_path = path / "delivery-validation.json"
    if not manifest_path.is_file() or not validation_path.is_file():
        raise DeliveryError("REUSE_SOURCE_INVALID")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeliveryError("REUSE_SOURCE_INVALID") from exc
    if validation.get("status") != "passed" or manifest.get("output_mode") != OUTPUT_MODE:
        raise DeliveryError("REUSE_SOURCE_INVALID")
    return manifest


def _verify_existing(path: Path, input_fingerprint: str) -> dict[str, Any]:
    validation_path = path / "delivery-validation.json"
    manifest_path = path / "page-text-manifest.json"
    if not validation_path.is_file() or not manifest_path.is_file():
        raise DeliveryError("OUTPUT_EXISTS_UNVERIFIED")
    required_package_files = (
        path / "book-text.md",
        path / "delivery-notes.md",
        path / "contact-sheet.png",
        path / "phase-events.json",
    )
    if not all(item.is_file() for item in required_package_files):
        raise DeliveryError("OUTPUT_EXISTS_CORRUPT")
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeliveryError("OUTPUT_EXISTS_CORRUPT") from exc
    if validation.get("input_fingerprint") != input_fingerprint:
        raise DeliveryError("OUTPUT_EXISTS_DIFFERENT_INPUT")
    if validation.get("page_count") != len(manifest.get("pages", [])):
        raise DeliveryError("OUTPUT_EXISTS_CORRUPT")
    for page in manifest.get("pages", []):
        image = path / page["output_path"]
        text = path / page["text_path"]
        if not image.is_file() or not text.is_file():
            raise DeliveryError("OUTPUT_EXISTS_CORRUPT")
        if _sha256(image) != page.get("output_sha256") or _sha256(text) != page.get("text_sha256"):
            raise DeliveryError("OUTPUT_EXISTS_CORRUPT")
    return {
        "status": "reused",
        "output_mode": OUTPUT_MODE,
        "output": str(path),
        "page_count": len(manifest.get("pages", [])),
        "cache_hits": len(manifest.get("pages", [])),
        "model_generation_calls": 0,
    }


def _book_text(title: str, age_band: str, pages: list[dict[str, Any]]) -> str:
    lines = [f"# 《{title}》", "", f"目标年龄：{age_band}", "", "## 封面", "", "封面由用户人工设计，不额外调用生图模型。", "", "## 正文", ""]
    for page in pages:
        lines.extend([f"### 第{int(page['page'])}页", "", str(page["text"]).strip(), ""])
    return "\n".join(lines)


def build_delivery(
    project: str | Path,
    book_id: str,
    output: str | Path,
    *,
    version: str | None = None,
    reuse_from: str | Path | None = None,
) -> dict[str, Any]:
    root = _project_root(project)
    book_dir = _book_dir(root, book_id, version)
    contract = _load_delivery_contract(root, book_dir, book_id)
    storyboard, pages = contract.storyboard, contract.pages
    source_records: list[dict[str, Any]] = []
    for page in pages:
        source = _source_image(root, book_dir, page, content_dir=contract.content_dir)
        width, height, source_sha256 = _inspect_image(source)
        source_records.append(
            {
                "page": page,
                "source": source,
                "source_width": width,
                "source_height": height,
                "source_sha256": source_sha256,
            }
        )
    input_fingerprint = _canonical_hash(
        {
            "output_mode": OUTPUT_MODE,
            "canvas": [WIDTH, HEIGHT],
            "storyboard": storyboard,
            "contract": {
                "layout": contract.layout,
                "business_book_id": contract.business_book_id,
                "age_band": contract.age_band,
                "input_hashes": contract.input_hashes,
            },
            "pages": [
                {
                    "page": int(record["page"]["page"]),
                    "source_sha256": record["source_sha256"],
                    "source_size": [record["source_width"], record["source_height"]],
                }
                for record in source_records
            ],
        }
    )
    output_path = Path(output).resolve()
    if output_path.exists():
        return _verify_existing(output_path, input_fingerprint)

    previous_manifest = _load_previous_manifest(Path(reuse_from).resolve()) if reuse_from else None
    previous_by_page = {int(item["page"]): item for item in (previous_manifest or {}).get("pages", [])}
    stage = output_path.parent / f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    stage.mkdir(parents=True, exist_ok=False)
    recorder = PhaseRecorder(stage / "phase-events.json", load_existing=False)
    overall_id = recorder.start("pure-image-delivery", task_id=f"{contract.business_book_id}:{book_dir.name}")
    try:
        prep_id = recorder.start("page-preparation", task_id=book_id)
        recorder.finish(prep_id, status="passed")
        image_id = recorder.start("image-postprocess", task_id=book_id)
        manifest_pages: list[dict[str, Any]] = []
        cache_hits = 0
        image_dir = stage / "images"
        text_dir = stage / "text"
        image_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)
        for record in source_records:
            page = record["page"]
            number = int(page["page"])
            page_fingerprint = _canonical_hash(
                {
                    "page": page,
                    "source_sha256": record["source_sha256"],
                    "source_size": [record["source_width"], record["source_height"]],
                    "output_size": [WIDTH, HEIGHT],
                }
            )
            output_image = image_dir / f"page-{number:02d}.png"
            output_text = text_dir / f"page-{number:02d}.txt"
            previous = previous_by_page.get(number)
            previous_image = Path(reuse_from).resolve() / previous["output_path"] if previous and reuse_from else None
            if previous and previous.get("page_fingerprint") == page_fingerprint and previous_image and previous_image.is_file() and _sha256(previous_image) == previous.get("output_sha256"):
                shutil.copyfile(previous_image, output_image)
                action = "reused"
                cache_hits += 1
            else:
                _write_normalized(record["source"], output_image)
                action = "normalized"
            _write_text(output_text, str(page["text"]).strip() + "\n")
            with Image.open(output_image) as image:
                if image.size != (WIDTH, HEIGHT):
                    raise DeliveryError(f"OUTPUT_DIMENSIONS_INVALID:{number}")
            manifest_pages.append(
                {
                    "page": number,
                    "page_id": page.get("page_id") or f"PAGE-{number:02d}",
                    "page_version": page.get("page_version"),
                    "text_path": f"text/page-{number:02d}.txt",
                    "image_source_path": record["source"].relative_to(root).as_posix() if record["source"].is_relative_to(root) else str(record["source"]),
                    "output_path": f"images/page-{number:02d}.png",
                    "text_sha256": _sha256(output_text),
                    "source_sha256": record["source_sha256"],
                    "output_sha256": _sha256(output_image),
                    "source_dimensions": [record["source_width"], record["source_height"]],
                    "output_dimensions": [WIDTH, HEIGHT],
                    "page_fingerprint": page_fingerprint,
                    "build_action": action,
                }
            )
        recorder.finish(image_id, status="passed")

        text_id = recorder.start("text-package", task_id=book_id)
        title = str(storyboard.get("title") or contract.business_book_id)
        age_band = contract.age_band
        _write_text(stage / "book-text.md", _book_text(title, age_band, pages))
        _write_json(
            stage / "page-text-manifest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "output_mode": OUTPUT_MODE,
                "book_id": contract.business_book_id,
                "version": book_dir.name,
                "title": title,
                "age_band": age_band,
                "canvas": {"width_px": WIDTH, "height_px": HEIGHT, "source_aspect_ratio": ASPECT_RATIO},
                "pages": manifest_pages,
            },
        )
        _write_text(
            stage / "delivery-notes.md",
            "\n".join(
                [
                    "# 纯图交付说明",
                    "",
                    "- 本工作包只包含无字插画、逐页正文和可追溯清单。",
                    "- 图片固定为1080×1440、3:4竖版；正文没有烧录进图片。",
                    "- 封面由用户人工设计；如复用某页插画，必须保留该页原故事用途。",
                    "- 本入口不调用图片模型、不生成PowerPoint、不自动合成字幕。",
                    "- 画面是否真正无字、角色/科学事实和审美质量仍需人工或模型视觉审核。",
                    "",
                ]
            ),
        )
        recorder.finish(text_id, status="passed")

        review_id = recorder.start("contact-sheet-generated", task_id=book_id)
        render_contact_sheet(stage / "images", stage / "contact-sheet.png", expected_pages=[int(page["page"]) for page in pages])
        recorder.finish(review_id, status="passed")

        summary = summarize_phase_events(recorder.events)
        validation = {
            "schema_version": SCHEMA_VERSION,
            "status": "passed",
            "release_status": "human_review_pending",
            "output_mode": OUTPUT_MODE,
            "input_fingerprint": input_fingerprint,
            "book_id": contract.business_book_id,
            "version": book_dir.name,
            "page_count": len(manifest_pages),
            "contract": {
                "layout": contract.layout,
                "content_root": contract.content_dir.relative_to(root).as_posix(),
                "business_book_id": contract.business_book_id,
                "inputs": sorted(contract.input_hashes),
                "input_hashes": contract.input_hashes,
            },
            "checks": {
                "page_order_matches_storyboard": [item["page"] for item in manifest_pages] == [int(page["page"]) for page in pages],
                "all_images_exact_1080x1440": all(item["output_dimensions"] == [WIDTH, HEIGHT] for item in manifest_pages),
                "all_page_texts_present": all((stage / item["text_path"]).is_file() for item in manifest_pages),
                "source_hashes_recorded": all(bool(item["source_sha256"]) for item in manifest_pages),
                "output_hashes_recorded": all(bool(item["output_sha256"]) for item in manifest_pages),
                "no_powerpoint_files": not any(path.suffix.lower() == ".pptx" for path in stage.rglob("*")),
                "contract_inputs_loaded": bool(contract.input_hashes),
                "model_generation_calls": 0,
                "visual_text_absence": "human_review_required",
                "visual_quality": "human_review_required",
            },
            "timing": summary,
        }
        _write_json(stage / "delivery-validation.json", validation)
        recorder.finish(overall_id, status="passed")
        # Rewrite validation after the final phase event is closed.
        validation["timing"] = summarize_phase_events(recorder.events)
        _write_json(stage / "delivery-validation.json", validation)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            raise DeliveryError("OUTPUT_CREATED_CONCURRENTLY")
        os.replace(stage, output_path)
        return {
            "status": "built",
            "output_mode": OUTPUT_MODE,
            "output": str(output_path),
            "page_count": len(manifest_pages),
            "cache_hits": cache_hits,
            "model_generation_calls": 0,
            "timing": validation["timing"],
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("book_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--reuse-from", type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_delivery(args.project, args.book_id, args.output, version=args.version, reuse_from=args.reuse_from)
    except (OSError, DeliveryError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

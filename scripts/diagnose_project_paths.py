"""Read-only diagnostic for project/storyboard image path compatibility.

The pure-image builder intentionally keeps a narrow search contract.  This
utility makes path mismatches visible without copying, renaming, converting,
or otherwise modifying a project.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_pure_image_delivery import (
    DeliveryError,
    _book_dir,
    _candidate_images,
    _project_root,
    _resolve_content_layout,
    _read_storyboard,
)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def _legacy_candidates(book_dir: Path, page_number: int) -> list[Path]:
    """Return images in the historical flat ``images`` directory."""

    directory = book_dir / "images"
    if not directory.is_dir():
        return []
    stem = f"page-{page_number:02d}"
    exact = [
        directory / f"{stem}{suffix}"
        for suffix in sorted(IMAGE_SUFFIXES)
        if (directory / f"{stem}{suffix}").is_file()
    ]
    if exact:
        return exact
    return sorted(
        path
        for path in directory.glob(f"{stem}-*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _path_record(path: Path, root: Path, *, current_builder_search: bool) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
        in_project = True
    except ValueError:
        in_project = False
    return {
        "path": str(resolved),
        "exists": resolved.is_file(),
        "in_project": in_project,
        "current_builder_search": current_builder_search,
    }


def diagnose_project_paths(project: str | Path, book_id: str, version: str | None = None) -> dict[str, Any]:
    """Inspect current and legacy image locations without writing any file."""

    root = _project_root(project)
    book_dir = _book_dir(root, book_id, version)
    content_dir, layout = _resolve_content_layout(book_dir)
    storyboard, pages = _read_storyboard(book_dir)
    search_dirs = [
        content_dir / "images" / "pages",
        content_dir / "illustrations",
        root / "deliverables" / "images-1080x1440",
    ]
    rows: list[dict[str, Any]] = []
    missing_pages: list[int] = []
    ambiguous_pages: list[int] = []
    legacy_available = False

    for page in pages:
        number = int(page["page"])
        current_candidates = _candidate_images(book_dir, root, page)
        legacy_candidates = _legacy_candidates(book_dir, number)
        if legacy_candidates:
            legacy_available = True
        if not current_candidates:
            missing_pages.append(number)
        elif len(current_candidates) > 1:
            ambiguous_pages.append(number)
        rows.append({
            "page": number,
            "declared_image": page.get("current_image_path"),
            "current_candidates": [
                _path_record(path, root, current_builder_search=True)
                for path in current_candidates
            ],
            "legacy_candidates": [
                _path_record(path, root, current_builder_search=False)
                for path in legacy_candidates
            ],
            "current_builder_search": bool(current_candidates),
            "legacy_available": bool(legacy_candidates),
        })

    status = "ok" if not missing_pages and not ambiguous_pages else "blocked"
    return {
        "schema_version": 1,
        "status": status,
        "project_root": str(root),
        "book_id": book_id,
        "version": version or book_dir.name,
        "book_dir": str(book_dir),
        "content_layout": layout,
        "content_root": str(content_dir),
        "storyboard_path": str(content_dir / "storyboard.json"),
        "storyboard_id": storyboard.get("book_id") if isinstance(storyboard, dict) else None,
        "story_page_count": len(pages),
        "current_builder_search_dirs": [str(path) for path in search_dirs],
        "current_builder_search": rows,
        "missing_pages": missing_pages,
        "ambiguous_pages": ambiguous_pages,
        "legacy_available": legacy_available,
        "write_operations": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        report = diagnose_project_paths(args.project, args.book_id, args.version)
    except DeliveryError as exc:
        print(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

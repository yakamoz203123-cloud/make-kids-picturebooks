"""Materialize the selected character references into a book-local generation plan."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from page_production import build_page_prompt


_AUXILIARY_REFERENCE_PURPOSES = frozenset({"action-reference", "group-reference"})


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_source(bundle_root: Path, relative: str) -> Path:
    source = (bundle_root / relative).resolve()
    try:
        source.relative_to(bundle_root.resolve())
    except ValueError as exc:
        raise ValueError(f"reference path escapes asset bundle: {relative}") from exc
    if not source.is_file():
        raise ValueError(f"selected reference does not exist: {relative}")
    return source


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def _asset_id_from_reference_id(reference_id: str) -> str:
    if reference_id.startswith("aux:"):
        return reference_id[4:]
    return reference_id.split(":", 1)[-1]


def prepare_page_references(
    page: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    bundle_root: str | Path,
    book_dir: str | Path,
    mode: str = "planning",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a page and copy only its selected references into the book.

    The returned page is ready for ``generation_queue.py``.  No image model is
    called; copied references are content-addressed by their actual SHA-256.
    """
    root = Path(bundle_root).resolve()
    book = Path(book_dir).resolve()
    selected = build_page_prompt(
        page,
        manifest=manifest,
        bundle_root=root,
        mode=mode,
    )["asset_selection"]
    references = selected.get("reference_selection", [])
    if not isinstance(references, list) or not references:
        raise ValueError("selected page has no character references")

    updated = copy.deepcopy(dict(page))
    materialized: list[dict[str, Any]] = []
    by_source: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in references:
        if not isinstance(reference, Mapping):
            raise ValueError("invalid resolved reference selection")
        source_relative = reference.get("reference_file")
        if not isinstance(source_relative, str) or not source_relative.strip():
            raise ValueError("resolved reference has no source path")
        source = _safe_source(root, source_relative)
        digest = _file_hash(source)
        key = (source_relative.replace("\\", "/"), digest)
        if key in by_source:
            continue
        destination = book / "characters" / str(manifest["bundle_id"]) / "reference" / f"{digest[:12]}-{source.name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or _file_hash(destination) != digest:
            shutil.copyfile(source, destination)
        relative_destination = destination.relative_to(book).as_posix()
        record = {
            "asset_id": _asset_id_from_reference_id(str(reference.get("reference_id", ""))),
            "path": relative_destination,
            "sha256": digest,
            "reference_purpose": str(reference.get("reference_purpose", "auxiliary-reference")),
            "source_reference_file": key[0],
        }
        by_source[key] = record
        materialized.append(record)

    identity = next((item for item in materialized if item["reference_purpose"] == "identity"), None)
    primary = identity or materialized[0]
    updated["character_asset_bundle"] = manifest["bundle_id"]
    updated["character_asset_version"] = manifest["version"]
    updated["characters_version"] = manifest["version"]
    updated["character_reference_path"] = primary["path"]
    updated["production_reference_path"] = primary["path"]
    updated["character_reference_assets"] = [
        item for item in materialized
        if item["reference_purpose"] in _AUXILIARY_REFERENCE_PURPOSES
    ]
    updated["resolved_asset_hash"] = selected["resolved_asset_hash"]
    updated["character_reference_manifest_hash"] = selected["manifest_content_hash"]
    return updated, {
        "manifest_content_hash": selected["manifest_content_hash"],
        "resolved_asset_hash": selected["resolved_asset_hash"],
        "references": materialized,
    }


def prepare_book_references(
    book_dir: str | Path,
    *,
    manifest_path: str | Path,
    bundle_root: str | Path,
    mode: str = "planning",
    write_manifest: bool = False,
) -> dict[str, Any]:
    book = Path(book_dir).resolve()
    manifest_file = Path(manifest_path).resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    page_manifest_path = book / "page-manifest.json"
    page_manifest = json.loads(page_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(page_manifest, dict) or not isinstance(page_manifest.get("pages"), list):
        raise ValueError("page-manifest.json must contain a pages list")
    updated_pages: list[dict[str, Any]] = []
    page_records: list[dict[str, Any]] = []
    for page in page_manifest["pages"]:
        updated, record = prepare_page_references(
            page,
            manifest=manifest,
            bundle_root=bundle_root,
            book_dir=book,
            mode=mode,
        )
        updated_pages.append(updated)
        page_records.append({"page": page.get("page"), **record})
    updated_manifest = copy.deepcopy(page_manifest)
    updated_manifest["pages"] = updated_pages
    result = {
        "schema_version": 1,
        "asset_bundle": manifest["bundle_id"],
        "asset_version": manifest["version"],
        "mode": mode,
        "page_count": len(updated_pages),
        "pages": page_records,
        "manifest_path": manifest_file.as_posix(),
        "bundle_root": Path(bundle_root).resolve().as_posix(),
    }
    _write_json_atomic(book / "generation-reference-plan.json", result)
    if write_manifest:
        _write_json_atomic(page_manifest_path, updated_manifest)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_dir", type=Path)
    parser.add_argument("--asset-manifest", required=True, type=Path)
    parser.add_argument("--asset-bundle-root", required=True, type=Path)
    parser.add_argument("--mode", choices=("planning", "production"), default="planning")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    result = prepare_book_references(
        args.book_dir,
        manifest_path=args.asset_manifest,
        bundle_root=args.asset_bundle_root,
        mode=args.mode,
        write_manifest=args.write_manifest,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

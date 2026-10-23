"""Build a traceable, non-nested incremental audit archive.

The archive is intentionally separate from the pure-image delivery builder.
Delivery files are copied as a self-contained subtree; audit evidence may
reference a single copied file when the same bytes occur more than once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

from build_pure_image_delivery import (
    DeliveryError,
    _book_dir,
    _book_key,
    _load_delivery_contract,
    _project_root,
    _resolve_content_layout,
    _source_image,
)


SCHEMA_VERSION = 1
EXCLUDED_DIR_NAMES = {"archive", "trial-archive-v1", "trial-archive", ".git"}


class ArchiveError(ValueError):
    """A deterministic archive input or commit failure."""


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
        raise ArchiveError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ArchiveError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _source_label(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _walk_files(root: Path, *, excluded: set[str] = EXCLUDED_DIR_NAMES) -> list[Path]:
    if not root.is_dir():
        return []
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        result.append(path)
    return result


def _book_specific_delivery_path(root: Path, book_dir: Path, delivery: Path) -> bool:
    """Return whether a legacy package is structurally scoped to this book."""

    book_key = book_dir.parent.name
    for scoped_root in (
        book_dir,
        root / "books" / book_key,
        root / "pure-image-delivery" / book_key,
        root / "delivery" / book_key,
        root / "deliveries" / book_key,
    ):
        if _inside(delivery, scoped_root):
            return True
    return False


def _delivery_identity_error(reason: str) -> ArchiveError:
    return ArchiveError(f"ARCHIVE_DELIVERY_IDENTITY_MISMATCH:{reason}")


def _validate_delivery_candidate(
    root: Path,
    book_dir: Path,
    contract: Any,
    directory: Path,
) -> None:
    """Validate delivery identity and source provenance against current inputs."""

    validation = _read_json(directory / "delivery-validation.json")
    manifest = _read_json(directory / "page-text-manifest.json")
    if validation.get("status") != "passed":
        raise _delivery_identity_error("status")
    if validation.get("output_mode") != "pure-images" or manifest.get("output_mode") != "pure-images":
        raise _delivery_identity_error("output_mode")
    if not validation.get("input_fingerprint"):
        raise _delivery_identity_error("input_fingerprint_missing")

    expected_key = book_dir.parent.name
    expected_version = book_dir.name
    expected_business_id = str(contract.business_book_id)
    validation_book_id = str(validation.get("book_id") or "").strip()
    manifest_book_id = str(manifest.get("book_id") or "").strip()
    validation_version = str(validation.get("version") or "").strip()
    manifest_version = str(manifest.get("version") or "").strip()
    if validation_version != expected_version or manifest_version != expected_version:
        raise _delivery_identity_error("version")

    contract_record = validation.get("contract")
    strict_contract = isinstance(contract_record, Mapping) and bool(contract_record.get("business_book_id"))
    if strict_contract:
        if validation_book_id != expected_business_id or manifest_book_id != expected_business_id:
            raise _delivery_identity_error("business_book_id")
        if str(contract_record.get("business_book_id")) != expected_business_id:
            raise _delivery_identity_error("contract.business_book_id")
        expected_content_root = _source_label(contract.content_dir, root)
        if contract_record.get("content_root") != expected_content_root:
            raise _delivery_identity_error("content_root")
        recorded_hashes = contract_record.get("input_hashes")
        if not isinstance(recorded_hashes, Mapping):
            raise _delivery_identity_error("contract.input_hashes")
        differing_inputs = {
            key
            for key in set(recorded_hashes) | set(contract.input_hashes)
            if recorded_hashes.get(key) != contract.input_hashes.get(key)
        }
        # Historical projects update project status metadata after delivery;
        # content and page-source changes must still invalidate the package.
        if differing_inputs - {"project.json"}:
            raise _delivery_identity_error("contract.input_hashes")
    else:
        # v1 delivery packages did not carry the full business id or contract.
        # They remain readable only when both manifests identify the directory
        # key and the package is physically scoped to that key.
        if validation_book_id != expected_key or manifest_book_id != expected_key:
            raise _delivery_identity_error("legacy_book_key")
        if not _book_specific_delivery_path(root, book_dir, directory):
            raise _delivery_identity_error("legacy_shared_path")

    expected_pages = [int(page["page"]) for page in contract.pages]
    if validation.get("page_count") != len(expected_pages):
        raise _delivery_identity_error("page_count")
    manifest_pages = manifest.get("pages")
    if not isinstance(manifest_pages, list) or [int(item.get("page", -1)) for item in manifest_pages] != expected_pages:
        raise _delivery_identity_error("page_order")
    if not validation.get("checks", {}).get("source_hashes_recorded"):
        raise _delivery_identity_error("source_hashes_not_recorded")

    for expected_page, delivered_page in zip(contract.pages, manifest_pages):
        number = int(expected_page["page"])
        try:
            source = _source_image(root, book_dir, expected_page, content_dir=contract.content_dir)
        except (DeliveryError, OSError, ValueError) as exc:
            raise _delivery_identity_error(f"formal_image_missing:{number}") from exc
        current_sha256 = _sha256(source)
        if delivered_page.get("source_sha256") != current_sha256:
            raise _delivery_identity_error(f"source_sha256:{number}")
        source_path = delivered_page.get("image_source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            raise _delivery_identity_error(f"source_path_missing:{number}")
        declared_source = Path(source_path)
        if not declared_source.is_absolute():
            declared_source = root / declared_source
        if declared_source.resolve() != source.resolve() and (
            strict_contract or not _book_specific_delivery_path(root, book_dir, declared_source)
        ):
            raise _delivery_identity_error(f"source_path:{number}")
        output_path = delivered_page.get("output_path")
        output_sha256 = delivered_page.get("output_sha256")
        if not isinstance(output_path, str) or not output_sha256:
            raise _delivery_identity_error(f"output_record_missing:{number}")
        output_file = (directory / output_path).resolve()
        if not _inside(output_file, directory) or not output_file.is_file() or _sha256(output_file) != output_sha256:
            raise _delivery_identity_error(f"output_sha256:{number}")
        expected_page_id = expected_page.get("page_id")
        if expected_page_id and delivered_page.get("page_id") not in (None, expected_page_id):
            raise _delivery_identity_error(f"page_id:{number}")


def _delivery_content_signature(directory: Path) -> tuple[Any, ...]:
    """Return the page-level evidence used to distinguish duplicate packages."""

    manifest = _read_json(directory / "page-text-manifest.json")
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        return ()
    return tuple(
        (
            item.get("page"),
            item.get("page_id"),
            item.get("source_sha256"),
            item.get("output_sha256"),
            item.get("text_sha256"),
            tuple(item.get("source_dimensions") or ()),
            tuple(item.get("output_dimensions") or ()),
        )
        for item in pages
    )


def _find_delivery(root: Path, book_dir: Path, contract: Any | None = None) -> Path | None:
    """Find exactly one delivery package proven to belong to ``book_dir``."""

    if contract is None:
        try:
            contract = _load_delivery_contract(root, book_dir, book_dir.parent.name)
        except (DeliveryError, OSError, ValueError) as exc:
            raise ArchiveError(f"ARCHIVE_CONTRACT_INVALID:{exc}") from exc

    valid: list[Path] = []
    valid_signatures: dict[Path, tuple[Any, ...]] = {}
    observed: list[str] = []
    reasons: list[str] = []
    for validation in root.rglob("delivery-validation.json"):
        if any(part in EXCLUDED_DIR_NAMES for part in validation.relative_to(root).parts):
            continue
        directory = validation.parent
        observed.append(_source_label(directory, root))
        try:
            _validate_delivery_candidate(root, book_dir, contract, directory)
        except ArchiveError as exc:
            reasons.append(f"{_source_label(directory, root)}:{exc}")
            continue
        valid.append(directory)
        valid_signatures[directory] = _delivery_content_signature(directory)

    if len(valid) > 1:
        if len({signature for signature in valid_signatures.values()}) > 1:
            raise ArchiveError("ARCHIVE_DELIVERY_AMBIGUOUS:" + ",".join(_source_label(path, root) for path in valid))
        # Identical page-level packages are safe historical duplicates. Pick
        # the most specific path deterministically without crossing books.
        valid.sort(key=lambda path: (len(path.parts), str(path)), reverse=True)
    if valid:
        return valid[0]
    if observed:
        detail = ";".join(reasons[:4])
        raise ArchiveError(f"ARCHIVE_DELIVERY_IDENTITY_MISMATCH:{detail}")
    return None


def _add_file(items: list[dict[str, Any]], path: Path, destination: str, use: str, *, root: Path, independent: bool = False) -> None:
    if not path.is_file():
        return
    resolved = path.resolve()
    if not _inside(resolved, root):
        return
    items.append({
        "use": use,
        "source_path": _source_label(resolved, root),
        "source_absolute_path": str(resolved),
        "archive_relative_path": destination.replace("\\", "/"),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
        "independent_delivery_file": independent,
    })


def _collect_items(root: Path, book_dir: Path, book_id: str, version: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    try:
        contract = _load_delivery_contract(root, book_dir, book_id)
        content_dir = contract.content_dir
    except (DeliveryError, OSError, ValueError) as exc:
        raise ArchiveError(f"ARCHIVE_CONTRACT_INVALID:{exc}") from exc
    items: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    _add_file(items, root / "project.json", "records/project.json", "project_contract", root=root)
    contract_names = ["story.md", "storyboard.json", "page-manifest.json", "page-text.json", "layout.json", "education-goal.json", "asset-binding-plan.json"]
    for name in contract_names:
        path = content_dir / name
        if path.is_file():
            _add_file(items, path, f"content/{name}", "current_content_contract", root=root)
    for page in contract.pages:
        number = int(page["page"])
        try:
            image = _source_image(root, book_dir, page, content_dir=content_dir)
        except (DeliveryError, OSError, ValueError) as exc:
            raise ArchiveError(f"ARCHIVE_FORMAL_IMAGE_MISSING:{number}:{exc}") from exc
        _add_file(items, image, f"final-images/page-{number:02d}{image.suffix.lower() or '.png'}", "formal_final_page", root=root)

    research_dir = root / "research"
    for path in _walk_files(research_dir):
        _add_file(items, path, f"research/{path.relative_to(research_dir).as_posix()}", "research_evidence", root=root)

    review_dir = book_dir / "review"
    candidate_dir = review_dir / "recovery-candidates"
    for path in _walk_files(review_dir):
        relative = path.relative_to(review_dir)
        if relative.parts and (relative.parts[0] == "recovery-candidates" or relative.parts[0] in {"formal-raw", "contact-sheet-input"}):
            continue
        _add_file(items, path, f"evidence/review/{relative.as_posix()}", "review_and_production_evidence", root=root)
    for path in _walk_files(candidate_dir, excluded=set()):
        relative = path.relative_to(candidate_dir)
        _add_file(items, path, f"recovery-candidates/{relative.as_posix()}", "approved_or_historical_recovery_candidate", root=root)

    for asset_root, use, destination_root in (
        (content_dir / "characters", "character_asset_evidence", "assets/characters"),
        (content_dir / "styles", "style_asset_evidence", "assets/styles"),
    ):
        for path in _walk_files(asset_root):
            _add_file(items, path, f"{destination_root}/{path.relative_to(asset_root).as_posix()}", use, root=root)

    try:
        delivery = _find_delivery(root, book_dir, contract)
    except ArchiveError:
        raise
    if delivery is not None:
        for path in _walk_files(delivery, excluded=set()):
            _add_file(
                items,
                path,
                f"delivery/{path.relative_to(delivery).as_posix()}",
                "independent_pure_image_delivery",
                root=root,
                independent=True,
            )
    else:
        raise ArchiveError("ARCHIVE_DELIVERY_MISSING")

    plan_path = content_dir / "asset-binding-plan.json"
    if plan_path.is_file():
        try:
            plan = _read_json(plan_path)
        except ArchiveError:
            plan = {}
        selected = plan.get("user_selected_assets") if isinstance(plan, Mapping) else None
        if isinstance(selected, Mapping):
            for key, value in selected.items():
                if not key.endswith("_path") or not isinstance(value, str) or not value.strip():
                    continue
                candidate = Path(value).resolve()
                if not _inside(candidate, root):
                    item = {"use": key, "source_path": str(candidate), "exists": candidate.is_file(), "sha256": _sha256(candidate) if candidate.is_file() else None}
                    external.append(item)

    fingerprint_payload = sorted(
        (
            {"use": item["use"], "source_path": item["source_path"], "sha256": item["sha256"], "size_bytes": item["size_bytes"], "archive_relative_path": item["archive_relative_path"], "independent_delivery_file": item["independent_delivery_file"]}
            for item in items
        ),
        key=lambda item: (item["archive_relative_path"], item["source_path"]),
    )
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return items, external, {"layout": contract.layout, "business_book_id": contract.business_book_id, "page_count": len(contract.pages), "input_fingerprint": fingerprint, "delivery_source": str(delivery) if delivery else None}


def _same_complete_archive(path: Path, fingerprint: str) -> bool:
    manifest_path = path / "ARCHIVE_MANIFEST.json"
    if not path.is_dir() or not manifest_path.is_file():
        return False
    try:
        manifest = _read_json(manifest_path)
    except ArchiveError:
        return False
    if manifest.get("status") != "complete" or manifest.get("input_fingerprint") != fingerprint:
        return False
    for entry in manifest.get("entries", []):
        if entry.get("independent_delivery_file") or entry.get("copied") is True:
            target = path / str(entry.get("archive_relative_path", ""))
            if not target.is_file() or _sha256(target) != entry.get("sha256"):
                return False
    return True


def _next_sibling(path: Path) -> Path:
    index = 2
    while True:
        candidate = path.with_name(f"{path.name}-v{index}")
        if not candidate.exists():
            return candidate
        index += 1


def build_incremental_archive(
    project: str | Path,
    book_id: str,
    target: str | Path,
    *,
    version: str | None = None,
    fail_after_copies: int | None = None,
) -> dict[str, Any]:
    """Create or safely reuse one archive without modifying the project."""
    root = _project_root(project)
    book_dir = _book_dir(root, book_id, version)
    items, external, metadata = _collect_items(root, book_dir, book_id, version)
    target_path = Path(target).resolve()
    if _same_complete_archive(target_path, metadata["input_fingerprint"]):
        manifest = _read_json(target_path / "ARCHIVE_MANIFEST.json")
        return {
            "status": "reused",
            "archive": str(target_path),
            "input_fingerprint": metadata["input_fingerprint"],
            "copied_file_count": manifest.get("stats", {}).get("copied_file_count", 0),
            "copied_bytes": manifest.get("stats", {}).get("copied_bytes", 0),
            "reused_file_count": manifest.get("stats", {}).get("reused_file_count", 0),
            "external_dependency_count": len(manifest.get("external_dependencies", [])),
        }
    if target_path.exists():
        target_path = _next_sibling(target_path)
    stage = target_path.parent / f".{target_path.name}.{uuid.uuid4().hex}.tmp"
    stage.mkdir(parents=True, exist_ok=False)
    copied_count = 0
    copied_bytes = 0
    reused_count = 0
    seen_sha: dict[str, str] = {}
    manifest_entries: list[dict[str, Any]] = []
    try:
        for item in items:
            source = Path(item["source_absolute_path"])
            sha = item["sha256"]
            destination = item["archive_relative_path"]
            independent = bool(item["independent_delivery_file"])
            reused_from = None
            copied = True
            if not independent and sha in seen_sha:
                copied = False
                reused_count += 1
                reused_from = seen_sha[sha]
            else:
                destination_path = stage / destination
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination_path)
                copied_count += 1
                copied_bytes += int(item["size_bytes"])
                if not independent:
                    seen_sha[sha] = destination
                if fail_after_copies is not None and copied_count >= fail_after_copies:
                    raise ArchiveError("ARCHIVE_SIMULATED_INTERRUPTION")
            entry = {key: item[key] for key in ("use", "source_path", "archive_relative_path", "sha256", "size_bytes", "independent_delivery_file")}
            entry.update({"copied": copied, "reused": not copied, "reused_from": reused_from, "external_dependencies": []})
            if independent:
                entry["reused"] = False
            manifest_entries.append(entry)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "complete",
            "archive_kind": "local_audit_with_independent_delivery",
            "project_root_at_build": str(root),
            "book_key": _book_key(root, book_id),
            "version": book_dir.name,
            "layout": metadata["layout"],
            "business_book_id": metadata["business_book_id"],
            "page_count": metadata["page_count"],
            "input_fingerprint": metadata["input_fingerprint"],
            "entries": manifest_entries,
            "external_dependencies": external,
            "stats": {
                "copied_file_count": copied_count,
                "copied_bytes": copied_bytes,
                "reused_file_count": reused_count,
                "source_file_count": len(items),
            },
            "model_generation_calls": 0,
            "formal_project_write_operations": 0,
        }
        _write_json(stage / "ARCHIVE_MANIFEST.json", manifest)
        hashes = {
            entry["archive_relative_path"]: entry["sha256"]
            for entry in manifest_entries
            if entry.get("copied") is True
        }
        _write_json(stage / "SHA256-MANIFEST.json", {"schema_version": 1, "files": hashes})
        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, target_path)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {
        "status": "built",
        "archive": str(target_path),
        "input_fingerprint": metadata["input_fingerprint"],
        "copied_file_count": copied_count,
        "copied_bytes": copied_bytes,
        "reused_file_count": reused_count,
        "external_dependency_count": len(external),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("book_id")
    parser.add_argument("target", type=Path)
    parser.add_argument("--version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build_incremental_archive(args.project, args.book_id, args.target, version=args.version)
    except (ArchiveError, DeliveryError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

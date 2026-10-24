"""Create a clean, reusable-input copy of a picturebook project for testing."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


_VERSION_DIR_RE = re.compile(r"^v\d+$", re.IGNORECASE)


def _is_excluded(relative: Path) -> bool:
    parts = relative.parts
    if relative.name == "PICTUREBOOK_TEST_REPORT.md":
        return True
    if "delivery" in parts or "recovery-candidates" in parts or "__pycache__" in parts:
        return True
    if relative.suffix.lower() == ".pyc":
        return True
    if relative.name == "production-queue.json" and "review" in parts:
        return True
    for index, part in enumerate(parts):
        if part == "images":
            if index > 0 and parts[index - 1].lower() == "content":
                return True
            if index > 0 and _VERSION_DIR_RE.fullmatch(parts[index - 1]):
                return True
    return False


def clone_project_for_test(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Copy reusable project inputs while excluding generated/runtime state."""

    source_root = Path(source).resolve()
    destination_root = Path(destination).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"source project does not exist: {source_root}")
    if not (source_root / "project.json").is_file():
        raise ValueError(f"source project is missing project.json: {source_root}")
    if destination_root.exists():
        raise FileExistsError(f"destination already exists: {destination_root}")

    destination_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination_root.name}-", dir=destination_root.parent))
    copied_files = 0
    excluded_files = 0
    try:
        for current, directories, files in os.walk(source_root, followlinks=False):
            current_root = Path(current)
            relative_root = current_root.relative_to(source_root)
            directories[:] = [
                name
                for name in directories
                if not _is_excluded(relative_root / name)
            ]
            target_root = staging / relative_root
            target_root.mkdir(parents=True, exist_ok=True)
            for name in files:
                relative = relative_root / name
                source_file = current_root / name
                if _is_excluded(relative):
                    excluded_files += 1
                    continue
                if source_file.is_symlink():
                    raise ValueError(f"source project contains unsupported symlink: {relative}")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target)
                copied_files += 1
        staging.replace(destination_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        "status": "copied",
        "source": str(source_root),
        "destination": str(destination_root),
        "copied_files": copied_files,
        "excluded_files": excluded_files,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = clone_project_for_test(args.source, args.destination)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

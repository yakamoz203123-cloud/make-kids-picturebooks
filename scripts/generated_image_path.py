"""Resolve a host image tool result to one concrete local PNG artifact."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_PATH_START_RE = re.compile(r"(?i)(?:[A-Za-z]:[\\/]|/)")
_PNG_END_RE = re.compile(r"(?i)\.png\b")


def _candidate_paths(value: str) -> list[Path]:
    """Return concrete-looking paths in input order without selecting one."""

    starts = list(_PATH_START_RE.finditer(value))
    candidates: list[Path] = []
    for index, match in enumerate(starts):
        segment_end = starts[index + 1].start() if index + 1 < len(starts) else len(value)
        segment = value[match.start() : segment_end]
        png_match = _PNG_END_RE.search(segment)
        if png_match is None:
            continue
        raw = segment[: png_match.end()].strip(" \t\r\n'\"`()[]{}<>,;:")
        if raw:
            candidates.append(Path(raw))

    # A direct relative path is useful in local wrappers and does not contain
    # an absolute path marker for the scanner above.
    stripped = value.strip().strip("'\"")
    if not starts and "\n" not in stripped and "\r" not in stripped:
        direct = Path(stripped)
        if direct.suffix.lower() == ".png":
            candidates.append(direct)
    return candidates


def extract_generated_image_path(value: str | Path, *, require_exists: bool = True) -> Path:
    """Resolve a direct path or host-tool prose to the final concrete PNG.

    Host tools may report both a generated-image directory and the actual
    ``exec-*.png`` file. The last concrete PNG path is the artifact; a
    directory-only report is never sufficient.
    """

    if isinstance(value, Path):
        candidates = [value]
    elif isinstance(value, str) and value.strip():
        candidates = _candidate_paths(value)
    else:
        candidates = []

    if not candidates:
        raise ValueError("generated image output must contain a concrete PNG path")

    selected = candidates[-1].expanduser()
    if selected.suffix.lower() != ".png":
        raise ValueError("generated image output must contain a concrete PNG path")
    resolved = selected.resolve()
    if require_exists and not resolved.is_file():
        raise FileNotFoundError(f"generated image does not exist: {resolved}")
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("value", help="a direct image path or host-tool output text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        path = extract_generated_image_path(args.value)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "resolved", "path": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Stable file hashing for released asset bundles."""

from __future__ import annotations

import hashlib
from pathlib import Path


TEXT_SUFFIXES = {".csv", ".json", ".md", ".toml", ".txt", ".yaml", ".yml"}


def canonical_bytes(path: str | Path) -> bytes:
    """Return bytes with platform line endings removed for UTF-8 text assets."""
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return raw
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def raw_file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matches_file_hash(path: str | Path, expected: str) -> bool:
    """Accept canonical hashes and pre-normalization v1 receipts."""
    expected = str(expected).lower()
    return expected in {file_hash(path), raw_file_hash(path)}

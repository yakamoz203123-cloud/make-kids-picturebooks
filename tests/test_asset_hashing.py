from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def test_text_asset_hash_is_stable_across_line_endings(tmp_path: Path) -> None:
    from asset_hashing import file_hash

    lf = tmp_path / "asset.json"
    crlf = tmp_path / "asset-crlf.json"
    lf.write_bytes(b'{"name": "windmill"}\n{"page": 1}\n')
    crlf.write_bytes(b'{"name": "windmill"}\r\n{"page": 1}\r\n')

    assert file_hash(lf) == file_hash(crlf)


def test_binary_asset_hash_preserves_raw_bytes(tmp_path: Path) -> None:
    from asset_hashing import file_hash, raw_file_hash

    first = tmp_path / "image.png"
    second = tmp_path / "image-copy.png"
    first.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01")
    second.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x02")

    assert file_hash(first) != file_hash(second)
    assert raw_file_hash(first) != raw_file_hash(second)


def test_legacy_raw_receipt_hash_remains_readable(tmp_path: Path) -> None:
    from asset_hashing import matches_file_hash, raw_file_hash

    asset = tmp_path / "legacy.json"
    asset.write_bytes(b'{"page": 1}\r\n')

    assert matches_file_hash(asset, raw_file_hash(asset))


@pytest.mark.parametrize(
    "relative",
    [
        "assets/characters/core-v1.2/manifest.json",
        "assets/characters/core-v1.3/asset-sources.json",
    ],
)
def test_checked_out_release_text_files_match_receipt_hash(relative: str) -> None:
    from asset_hashing import file_hash

    path = Path(__file__).parents[1] / relative
    assert path.is_file()
    assert file_hash(path) == _receipt_file_hash(path)


def _receipt_file_hash(path: Path) -> str:
    import json

    receipt = json.loads((path.parent / "manifest-receipt.json").read_text(encoding="utf-8"))
    return receipt["files"][path.relative_to(path.parent).as_posix()]

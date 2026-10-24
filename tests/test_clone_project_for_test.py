from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from clone_project_for_test import clone_project_for_test


def _write(path: Path, content: bytes = b"fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_clone_excludes_runtime_outputs_but_preserves_reusable_inputs(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "copy"

    _write(source / "project.json", b"{}")
    _write(source / "books/b01/v1/content/story.md", b"story")
    _write(source / "books/b01/v1/content/prompts/page-01.md", b"prompt")
    _write(source / "books/b01/v1/content/research/claims.json", b"{}")
    _write(source / "books/b01/v1/content/characters/core/reference.png", b"png")
    _write(source / "books/b01/v1/images/page-01.png", b"formal")
    _write(source / "books/b01/v1/content/images/page-01.png", b"preview")
    _write(source / "books/b01/v1/delivery/pure-image-delivery-v1/images/page-01.png", b"delivery")
    _write(source / "books/b01/v1/review/production-queue.json", b"{}")
    _write(source / "books/b01/v1/review/recovery-candidates/old.json", b"{}")
    _write(source / "PICTUREBOOK_TEST_REPORT.md", b"old report")

    result = clone_project_for_test(source, destination)

    assert result["status"] == "copied"
    assert (destination / "project.json").is_file()
    assert (destination / "books/b01/v1/content/story.md").is_file()
    assert (destination / "books/b01/v1/content/prompts/page-01.md").is_file()
    assert (destination / "books/b01/v1/content/research/claims.json").is_file()
    assert (destination / "books/b01/v1/content/characters/core/reference.png").is_file()
    assert not (destination / "books/b01/v1/images/page-01.png").exists()
    assert not (destination / "books/b01/v1/content/images/page-01.png").exists()
    assert not (destination / "books/b01/v1/delivery").exists()
    assert not (destination / "books/b01/v1/review/production-queue.json").exists()
    assert not (destination / "books/b01/v1/review/recovery-candidates").exists()
    assert not (destination / "PICTUREBOOK_TEST_REPORT.md").exists()


def test_clone_refuses_existing_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "copy"
    _write(source / "project.json", b"{}")
    destination.mkdir()

    with pytest.raises(FileExistsError, match="destination already exists"):
        clone_project_for_test(source, destination)


def test_clone_refuses_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError, match="source project does not exist"):
        clone_project_for_test(tmp_path / "missing", tmp_path / "copy")

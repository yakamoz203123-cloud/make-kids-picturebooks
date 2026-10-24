from __future__ import annotations

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from generated_image_path import extract_generated_image_path


def test_resolves_concrete_exec_png_from_host_tool_prose(tmp_path):
    artifact = tmp_path / "exec-1234.png"
    artifact.write_bytes(b"png")

    value = (
        f"Generated images are saved to {tmp_path} as {artifact} by default."
    )

    assert extract_generated_image_path(value) == artifact.resolve()


def test_accepts_direct_existing_path(tmp_path):
    artifact = tmp_path / "page-01.png"
    artifact.write_bytes(b"png")

    assert extract_generated_image_path(artifact) == artifact.resolve()


def test_selects_last_concrete_png_when_host_output_contains_multiple_artifacts(tmp_path):
    first = tmp_path / "exec-first.png"
    second = tmp_path / "exec-second.png"
    first.write_bytes(b"png")
    second.write_bytes(b"png")

    value = f"saved as {first}; retry output saved as {second}"

    assert extract_generated_image_path(value) == second.resolve()


def test_rejects_directory_only_output(tmp_path):
    with pytest.raises(ValueError, match="concrete PNG"):
        extract_generated_image_path(f"Generated images are saved to {tmp_path}")


def test_rejects_missing_concrete_png(tmp_path):
    missing = tmp_path / "exec-missing.png"

    with pytest.raises(FileNotFoundError, match="generated image does not exist"):
        extract_generated_image_path(f"Generated image: {missing}")

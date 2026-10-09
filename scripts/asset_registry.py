"""Collect only explicitly declared project assets."""

import json
from pathlib import Path

from project_paths import require_project_file, resolve_project_file


def _canonical(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _add_file(assets: set[str], root: Path, value: str | Path, label: str) -> Path:
    path = require_project_file(root, value, label)
    assets.add(_canonical(root, path))
    return path


def _add_directory_files(
    assets: set[str], root: Path, value: str | Path, label: str, source_path: Path
) -> None:
    directory = resolve_project_file(root, value)
    if not directory.is_dir():
        raise ValueError(f"{label}目录缺失: {value}")
    try:
        source_path.parent.resolve().relative_to(directory)
    except ValueError:
        pass
    else:
        raise ValueError(f"{label}目录不得包含来源目录: {value}")
    for path in directory.rglob("*"):
        if path.is_file():
            resolved = path.resolve()
            try:
                assets.add(_canonical(root, resolved))
            except ValueError as exc:
                raise ValueError(f"{label}目录包含项目外文件: {path}") from exc


def _read_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}不可读取: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label}必须是对象: {path}")
    return data


def collect_declared_assets(project_path: Path, project: dict, book: dict) -> set[str]:
    """Return canonical paths for a book's declared, project-local assets only."""
    root = Path(project_path).resolve().parent
    if not isinstance(project, dict) or not isinstance(book, dict):
        raise ValueError("项目和册记录必须是对象")

    assets: set[str] = set()
    source = project.get("source")
    if not isinstance(source, dict) or not source.get("path"):
        raise ValueError("缺少显式来源文件")
    source_path = _add_file(assets, root, source["path"], "来源")

    artifacts = book.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("成果记录必须是对象")
    declared: dict[str, Path] = {}
    for label, value in artifacts.items():
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError(f"成果路径无效: {label}")
        declared[label] = _add_file(assets, root, value, f"成果 {label}")

    characters_path = project.get("characters_path")
    if characters_path:
        _add_directory_files(assets, root, characters_path, "角色参考", source_path)

    review_path = declared.get("review")
    if review_path:
        review = _read_json(review_path, "审核记录")
        for field in ("reading_pages", "print_sides"):
            records = review.get(field, [])
            if not isinstance(records, list):
                raise ValueError(f"审核记录 {field} 必须是数组")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"审核记录 {field} 包含非法条目")
                image_path = record.get("image_path")
                if image_path:
                    _add_file(assets, root, image_path, "审核渲染图")

    layout_path = declared.get("layout")
    if layout_path:
        layout = _read_json(layout_path, "版面记录")
        for field, label in (
            ("font_path", "字体"),
            ("font_license_path", "字体许可证"),
            ("font_provenance_path", "字体来源证明"),
        ):
            value = layout.get(field)
            if not isinstance(value, (str, Path)) or not str(value).strip():
                raise ValueError(f"缺少{label}")
            path = require_project_file(layout_path.parent, value, label)
            assets.add(_canonical(root, path))

    return assets

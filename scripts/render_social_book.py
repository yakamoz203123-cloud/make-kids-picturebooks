"""Render one social-only picturebook as a single Xiaohongshu image set."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from layout_design import get_social_profile, validate_layout_design
from render_social import render_social_page


SOCIAL_ONLY_OUTPUT_MODE = "social-only"
SOCIAL_ONLY_PROFILE = "xiaohongshu-feed-3x4"
SOCIAL_ONLY_CANVAS = {"width_px": 1080, "height_px": 1440}


def _resolve_path(value, base_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _relative_path(path: Path, base_dir: Path) -> str:
    try:
        return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _load_layout(layout_path: Path) -> dict:
    try:
        value = json.loads(layout_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"版面文件不存在: {layout_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"版面文件不是有效JSON: {layout_path}") from exc
    if not isinstance(value, dict):
        raise ValueError("版面文件必须是对象")
    return value


def _validated_pages(layout: dict) -> list[dict]:
    if layout.get("output_mode") != SOCIAL_ONLY_OUTPUT_MODE:
        raise ValueError("当前渲染器只接受output_mode=social-only")
    pages = layout.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("social-only版面必须包含非空pages列表")

    validated = []
    seen_numbers = set()
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("social-only页面必须是对象")
        number = page.get("number")
        if type(number) is not int or number <= 0 or number in seen_numbers:
            raise ValueError("social-only页面number必须是唯一正整数")
        seen_numbers.add(number)
        design = page.get("layout_design")
        errors = validate_layout_design(design, require_complete=True)
        if errors:
            raise ValueError(f"第{number}页layout_design无效: {'; '.join(errors)}")
        social_layout = design["social_layout"]
        if social_layout["profile"] != SOCIAL_ONLY_PROFILE:
            raise ValueError(
                f"第{number}页必须使用{SOCIAL_ONLY_PROFILE}，不再输出其他社媒profile"
            )
        if design.get("layout_mode") != "scene-integrated":
            raise ValueError(
                f"第{number}页social-only必须使用scene-integrated，不能使用大块文字卡"
            )
        if social_layout.get("text_placement") != "in-scene":
            raise ValueError(f"第{number}页文字必须位于画面内部(in-scene)")
        if not isinstance(page.get("text", ""), str):
            raise ValueError(f"第{number}页正文必须是字符串")
        source_value = page.get("image_path") or page.get("image")
        if not source_value:
            raise ValueError(f"第{number}页缺少image_path或image")
        validated.append(page)

    return sorted(validated, key=lambda item: item["number"])


def render_social_book(layout_path, output_dir) -> dict:
    """Render a complete social-only book atomically.

    The image model supplies the illustration without text. ``render_social_page``
    then rasterizes the editable copy onto the same 1080x1440 canvas. The result
    is one flattened social image per page; this function never creates PDFs,
    print booklets, 9:16 pages, or alternate versions.
    """

    layout_path = Path(layout_path).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(output_dir)
    layout = _load_layout(layout_path)
    pages = _validated_pages(layout)
    base_dir = layout_path.parent
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    staging_path = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    manifest_pages = []
    try:
        for page in pages:
            number = page["number"]
            source = _resolve_path(page.get("image_path") or page.get("image"), base_dir)
            if not source.is_file():
                raise ValueError(f"第{number}页社媒源图不存在: {source}")

            render_page = dict(page)
            render_page["image_path"] = source
            if layout.get("age_band") and not render_page.get("age_band"):
                render_page["age_band"] = layout["age_band"]
            font_value = page.get("font_path") or layout.get("font_path")
            if font_value:
                render_page["font_path"] = _resolve_path(font_value, base_dir)
            target = staging_path / f"page-{number:02d}.png"
            layout_info = {}
            render_social_page(render_page, target, layout_info=layout_info)
            manifest_pages.append(
                {
                    "number": number,
                    "output": target.name,
                    "source": _relative_path(source, base_dir),
                    "profile": SOCIAL_ONLY_PROFILE,
                    "canvas": dict(SOCIAL_ONLY_CANVAS),
                    "source_aspect_ratio": "3:4",
                    "layout_mode": "scene-integrated",
                    "text_placement": "in-scene",
                    "layout": layout_info,
                }
            )

        manifest = {
            "schema_version": 1,
            "output_mode": SOCIAL_ONLY_OUTPUT_MODE,
            "profile": SOCIAL_ONLY_PROFILE,
            "canvas": dict(SOCIAL_ONLY_CANVAS),
            "page_count": len(manifest_pages),
            "pages": manifest_pages,
            "pdf_outputs": [],
            "print_outputs": [],
        }
        manifest_path = staging_path / "social-output.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staging_path.replace(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    manifest = render_social_book(args.layout_json, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

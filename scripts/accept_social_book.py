"""Deterministically accept one reviewed Xiaohongshu-only picturebook output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from PIL import Image

from layout_design import image_matches_aspect_ratio, validate_layout_design


PROFILE = "xiaohongshu-feed-3x4"
CANVAS = (1080, 1440)
OUTPUT_MODE = "social-only"


def _load_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label}不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}不是有效JSON: {path}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_evidence(record: dict, label: str) -> None:
    if not isinstance(record, dict) or record.get("status") != "passed":
        raise ValueError(f"{label}必须是passed")
    evidence = record.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError(f"{label}缺少具体evidence")


def _validate_review(review: dict, page_numbers: list[int]) -> None:
    if review.get("output_mode") != OUTPUT_MODE:
        raise ValueError("review必须声明output_mode=social-only")
    pages = review.get("social_pages")
    if not isinstance(pages, list) or [item.get("page") for item in pages] != page_numbers:
        raise ValueError("review.social_pages必须按顺序覆盖全部页面")
    for item in pages:
        if not isinstance(item, dict):
            raise ValueError("review.social_pages条目必须是对象")
        _require_evidence(item, f"第{item.get('page')}页social review")
        layout_review = item.get("layout_review")
        _require_evidence(layout_review, f"第{item.get('page')}页layout_review")
        if layout_review.get("text_image_relationship") != "integrated":
            raise ValueError(f"第{item.get('page')}页文字必须记录为integrated")

    _require_evidence(review.get("contact_sheet_review"), "contact_sheet_review")
    for key in ("engineering_evidence", "content_evidence", "visual_evidence"):
        _require_evidence(review.get(key), key)
    real_reading = review.get("real_reading_evidence")
    if not isinstance(real_reading, dict) or real_reading.get("status") not in {"passed", "pending"}:
        raise ValueError("real_reading_evidence必须是passed或pending")
    if review.get("unresolved_digital_defects") not in ([], None):
        raise ValueError("存在未解决的数字缺陷")


def _atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        suffix=".json", prefix=f".{path.stem}.", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def accept_social_book(layout_path, social_dir, review_path, acceptance_path) -> dict:
    """Validate files, dimensions and required human/model review records."""

    layout_path = Path(layout_path).resolve()
    social_dir = Path(social_dir).resolve()
    review_path = Path(review_path).resolve()
    acceptance_path = Path(acceptance_path).resolve()
    if acceptance_path.exists():
        raise FileExistsError(acceptance_path)

    layout = _load_json(layout_path, "layout")
    if layout.get("output_mode") != OUTPUT_MODE:
        raise ValueError("layout必须声明output_mode=social-only")
    pages = layout.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("layout必须包含非空pages列表")

    page_numbers = []
    page_by_number = {}
    for page in pages:
        if not isinstance(page, dict) or type(page.get("number")) is not int:
            raise ValueError("layout页面number必须是整数")
        number = page["number"]
        if number in page_by_number:
            raise ValueError(f"重复页面编号: {number}")
        errors = validate_layout_design(page.get("layout_design"), require_complete=True)
        if errors:
            raise ValueError(f"第{number}页layout_design无效: {'; '.join(errors)}")
        design = page["layout_design"]
        social = design["social_layout"]
        if social.get("profile") != PROFILE or social.get("text_placement") != "in-scene":
            raise ValueError(f"第{number}页不是当前小红书画内文字契约")
        if design.get("layout_mode") != "scene-integrated":
            raise ValueError(f"第{number}页不是scene-integrated")
        page_numbers.append(number)
        page_by_number[number] = page
    page_numbers.sort()
    if page_numbers != list(range(1, len(page_numbers) + 1)):
        raise ValueError("页面编号必须从1连续排列")

    manifest = _load_json(social_dir / "social-output.json", "social-output.json")
    if manifest.get("output_mode") != OUTPUT_MODE or manifest.get("profile") != PROFILE:
        raise ValueError("social-output.json不是当前小红书单一输出")
    if manifest.get("canvas") != {"width_px": CANVAS[0], "height_px": CANVAS[1]}:
        raise ValueError("social-output.json画布必须是1080×1440")
    manifest_pages = manifest.get("pages")
    if not isinstance(manifest_pages, list) or [item.get("number") for item in manifest_pages] != page_numbers:
        raise ValueError("social-output.json页面清单与layout不一致")
    if manifest.get("pdf_outputs") != [] or manifest.get("print_outputs") != []:
        raise ValueError("当前成品不允许包含PDF或打印输出")

    files = {}
    for item in manifest_pages:
        number = item["number"]
        output_name = item.get("output")
        output = social_dir / output_name if isinstance(output_name, str) else None
        if output is None or not output.is_file():
            raise ValueError(f"第{number}页社媒成品不存在")
        try:
            with Image.open(output) as image:
                image.verify()
            with Image.open(output) as image:
                image.load()
                if image.size != CANVAS:
                    raise ValueError(f"第{number}页输出尺寸不是1080×1440")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"第{number}页输出不是可读图像: {exc}") from exc

        source_value = page_by_number[number].get("image_path") or page_by_number[number].get("image")
        source = Path(source_value)
        if not source.is_absolute():
            source = layout_path.parent / source
        if not source.is_file():
            raise ValueError(f"第{number}页源图不存在")
        with Image.open(source) as image:
            image.load()
            if not image_matches_aspect_ratio(image.width, image.height, "3:4"):
                raise ValueError(f"第{number}页源图不是原生3:4")

        files[output.relative_to(social_dir).as_posix()] = _sha256(output)

    review = _load_json(review_path, "review")
    _validate_review(review, page_numbers)

    result = {
        "schema_version": 1,
        "status": "passed",
        "digital_status": "digital_checked",
        "output_mode": OUTPUT_MODE,
        "profile": PROFILE,
        "canvas": {"width_px": CANVAS[0], "height_px": CANVAS[1]},
        "page_count": len(page_numbers),
        "files": files,
        "pdf_outputs": [],
        "print_outputs": [],
        "real_reading_status": review["real_reading_evidence"]["status"],
    }
    _atomic_write_json(acceptance_path, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout_json", type=Path)
    parser.add_argument("social_dir", type=Path)
    parser.add_argument("review_json", type=Path)
    parser.add_argument("acceptance_json", type=Path)
    args = parser.parse_args(argv)
    result = accept_social_book(
        args.layout_json, args.social_dir, args.review_json, args.acceptance_json
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

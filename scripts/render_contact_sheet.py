"""Create a deterministic, labelled thumbnail wall for a picturebook.

This utility is a visual-review aid.  It checks that the supplied page files
are readable images and that page numbers are contiguous, but it does not
judge the aesthetic quality of the artwork or layout.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps


PAGE_NAME_RE = re.compile(r"^page-(\d+)$", re.IGNORECASE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

DEFAULT_COLUMNS = 3
DEFAULT_THUMB_WIDTH = 320
DEFAULT_THUMB_HEIGHT = 453
DEFAULT_LABEL_HEIGHT = 40
DEFAULT_MARGIN = 24
DEFAULT_GAP = 16


@dataclass(frozen=True)
class PageImage:
    """A validated page image and its numeric page number."""

    page_number: int
    path: Path


def _page_number(path: Path) -> int | None:
    match = PAGE_NAME_RE.fullmatch(path.stem)
    if match is None:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def _validate_image(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ValueError("图像尺寸必须为正数")
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) == "图像尺寸必须为正数":
            detail = str(exc)
        else:
            detail = str(exc) or exc.__class__.__name__
        raise ValueError(f"无法读取图像 {path.name}: {detail}") from exc


def discover_page_images(
    input_dir: str | os.PathLike[str],
    *,
    expected_page_count: int | None = None,
    expected_pages: Sequence[int] | None = None,
) -> list[PageImage]:
    """Validate and return contiguous ``page-N`` PNG/JPEG files in page order.

    The directory is intentionally strict: every direct file must be a page
    image.  This prevents notes, stale exports, and corrupted page artifacts
    from silently entering the visual-review contact sheet.
    """

    directory = Path(input_dir)
    if not directory.is_dir():
        raise ValueError(f"reading-pages目录不存在或不是目录: {directory}")
    if expected_page_count is not None and expected_pages is not None:
        raise ValueError("expected_page_count与expected_pages不能同时使用")
    if expected_page_count is not None and (
        type(expected_page_count) is not int or expected_page_count <= 0
    ):
        raise ValueError("expected_page_count必须是正整数")
    normalized_expected_pages: list[int] | None = None
    if expected_pages is not None:
        normalized_expected_pages = sorted(set(expected_pages))
        if not normalized_expected_pages or any(type(number) is not int or number <= 0 for number in normalized_expected_pages):
            raise ValueError("expected_pages必须是正整数数组")

    discovered: list[PageImage] = []
    seen_numbers: set[int] = set()
    entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    for entry in entries:
        if not entry.is_file():
            raise ValueError(f"非图像输入或目录输入: {entry.name}")
        number = _page_number(entry)
        if number is None:
            raise ValueError(f"非图像输入或非页面输入: {entry.name}")
        if entry.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(f"非图像输入: {entry.name}（页面文件必须是 PNG/JPEG）")
        if number in seen_numbers:
            raise ValueError(f"重复页面编号: {number}")
        seen_numbers.add(number)
        _validate_image(entry)
        discovered.append(PageImage(number, entry))

    if not discovered:
        raise ValueError("未找到 page-*.png/jpg/jpeg 页面图像")

    discovered.sort(key=lambda item: item.page_number)
    if normalized_expected_pages is not None:
        missing = [number for number in normalized_expected_pages if number not in seen_numbers]
        extras = [item.page_number for item in discovered if item.page_number not in set(normalized_expected_pages)]
    else:
        last_number = discovered[-1].page_number
        expected_last = expected_page_count or last_number
        missing = [
            number
            for number in range(1, expected_last + 1)
            if number not in seen_numbers
        ]
        extras = [item.page_number for item in discovered if expected_page_count is not None and item.page_number > expected_page_count]
    if missing:
        missing_text = ", ".join(str(number) for number in missing)
        raise ValueError(f"缺少页面: {missing_text}")
    if extras:
        label = "expected_pages" if normalized_expected_pages is not None else "expected_page_count"
        raise ValueError(f"页面数量超过{label}: {extras}")
    return discovered


def contact_sheet_size(
    page_count: int,
    *,
    columns: int = DEFAULT_COLUMNS,
    thumb_width: int = DEFAULT_THUMB_WIDTH,
    thumb_height: int = DEFAULT_THUMB_HEIGHT,
    label_height: int = DEFAULT_LABEL_HEIGHT,
    margin: int = DEFAULT_MARGIN,
    gap: int = DEFAULT_GAP,
) -> tuple[int, int]:
    """Return the exact RGB canvas size for the requested grid geometry."""

    _validate_geometry(
        page_count,
        columns=columns,
        thumb_width=thumb_width,
        thumb_height=thumb_height,
        label_height=label_height,
        margin=margin,
        gap=gap,
    )
    rows = (page_count + columns - 1) // columns
    width = margin * 2 + columns * thumb_width + (columns - 1) * gap
    height = margin * 2 + rows * (thumb_height + label_height) + (rows - 1) * gap
    return width, height


def _validate_geometry(
    page_count: int,
    *,
    columns: int,
    thumb_width: int,
    thumb_height: int,
    label_height: int,
    margin: int,
    gap: int,
) -> None:
    if type(page_count) is not int or page_count <= 0:
        raise ValueError("page_count必须是正整数")
    positive = {
        "columns": columns,
        "thumb_width": thumb_width,
        "thumb_height": thumb_height,
        "label_height": label_height,
    }
    for name, value in positive.items():
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name}必须是正整数")
    for name, value in {"margin": margin, "gap": gap}.items():
        if type(value) is not int or value < 0:
            raise ValueError(f"{name}必须是非负整数")


def _load_font(label_height: int) -> ImageFont.ImageFont:
    font_path = Path(__file__).resolve().parents[1] / "assets" / "kidsbook-print.ttf"
    font_size = max(1, round(label_height * 0.55))
    if font_path.is_file():
        try:
            return ImageFont.truetype(str(font_path), font_size)
        except OSError:
            pass
    return ImageFont.load_default()


def _save_atomically(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        suffix=output_path.suffix.lower(), dir=output_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        if output_path.suffix.lower() in {".jpg", ".jpeg"}:
            image.save(temporary_path, format="JPEG", quality=95, optimize=False)
        else:
            image.save(temporary_path, format="PNG", optimize=False)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def render_contact_sheet(
    input_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    expected_page_count: int | None = None,
    expected_pages: Sequence[int] | None = None,
    columns: int = DEFAULT_COLUMNS,
    thumb_width: int = DEFAULT_THUMB_WIDTH,
    thumb_height: int = DEFAULT_THUMB_HEIGHT,
    label_height: int = DEFAULT_LABEL_HEIGHT,
    margin: int = DEFAULT_MARGIN,
    gap: int = DEFAULT_GAP,
) -> Path:
    """Render a labelled contact sheet and return its output path.

    Images are letterboxed into fixed thumbnail cells; no source page is
    cropped.  Existing outputs are never overwritten.  The result is a
    review artifact only and does not represent an aesthetic approval.
    """

    output = Path(output_path)
    if output.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("缩略图墙输出必须是 PNG 或 JPEG")
    if output.exists():
        raise FileExistsError(output)

    pages = discover_page_images(
        input_dir,
        expected_page_count=expected_page_count,
        expected_pages=expected_pages,
    )
    width, height = contact_sheet_size(
        len(pages),
        columns=columns,
        thumb_width=thumb_width,
        thumb_height=thumb_height,
        label_height=label_height,
        margin=margin,
        gap=gap,
    )
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = _load_font(label_height)
    cell_height = thumb_height + label_height

    for index, page in enumerate(pages):
        row, column = divmod(index, columns)
        x = margin + column * (thumb_width + gap)
        y = margin + row * (cell_height + gap)
        with Image.open(page.path) as source:
            source_rgb = source.convert("RGB")
            try:
                thumbnail = ImageOps.contain(
                    source_rgb,
                    (thumb_width, thumb_height),
                    method=Image.Resampling.LANCZOS,
                )
            finally:
                source_rgb.close()
        try:
            paste_x = x + (thumb_width - thumbnail.width) // 2
            paste_y = y + (thumb_height - thumbnail.height) // 2
            sheet.paste(thumbnail, (paste_x, paste_y))
        finally:
            thumbnail.close()
        draw.rectangle(
            (x, y, x + thumb_width - 1, y + thumb_height - 1),
            outline=(210, 210, 210),
            width=1,
        )
        label_top = y + thumb_height
        draw.rectangle(
            (x, label_top, x + thumb_width - 1, label_top + label_height - 1),
            fill=(255, 255, 255),
        )
        label = f"Page {page.page_number:02d}"
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        text_width = right - left
        text_height = bottom - top
        text_x = x + (thumb_width - text_width) // 2 - left
        text_y = label_top + (label_height - text_height) // 2 - top
        draw.text((text_x, text_y), label, fill=(50, 50, 50), font=font)

    try:
        _save_atomically(sheet, output)
    finally:
        sheet.close()
    return output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a numbered picturebook thumbnail wall for visual review."
    )
    parser.add_argument("input_dir", type=Path, help="reading-pages directory")
    parser.add_argument("output_path", type=Path, help="PNG/JPEG contact-sheet output")
    parser.add_argument("--page-count", type=int, dest="expected_page_count")
    parser.add_argument("--columns", type=int, default=DEFAULT_COLUMNS)
    parser.add_argument("--thumb-width", type=int, default=DEFAULT_THUMB_WIDTH)
    parser.add_argument("--thumb-height", type=int, default=DEFAULT_THUMB_HEIGHT)
    parser.add_argument("--label-height", type=int, default=DEFAULT_LABEL_HEIGHT)
    parser.add_argument("--margin", type=int, default=DEFAULT_MARGIN)
    parser.add_argument("--gap", type=int, default=DEFAULT_GAP)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = render_contact_sheet(
            args.input_dir,
            args.output_path,
            expected_page_count=args.expected_page_count,
            columns=args.columns,
            thumb_width=args.thumb_width,
            thumb_height=args.thumb_height,
            label_height=args.label_height,
            margin=args.margin,
            gap=args.gap,
        )
    except (FileExistsError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

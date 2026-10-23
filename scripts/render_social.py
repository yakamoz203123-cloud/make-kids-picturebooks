"""Render one reviewed social page without cropping a print page."""

import math
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from layout_design import (
    get_social_profile,
    image_matches_aspect_ratio,
    validate_layout_design,
)
from layout_styles import (
    SOCIAL_BAND_RADIUS_PX,
    SOCIAL_CARD_RADIUS_PX,
    SOCIAL_TEXT_PADDING_PX,
    resolve_text_style,
)


_PROFILE_OMITTED = object()

_LINE_START_FORBIDDEN = "，。！？：；、”’）》】》…"
_LINE_END_FORBIDDEN = "“‘（【「『〈《"
SOCIAL_MIN_FONT_SIZE = 32


def _pixel_box(area, width, height):
    x, y, box_width, box_height = area
    result = (
        round(x * width),
        round(y * height),
        round((x + box_width) * width),
        round((y + box_height) * height),
    )
    if result[0] < 0 or result[1] < 0 or result[2] > width or result[3] > height:
        raise ValueError("社媒元素超出画布")
    return result


def _wrap_text(text, draw, font, width):
    """Wrap Chinese copy using measured glyph widths and punctuation rules."""
    if width <= 0:
        raise ValueError("字幕超出文字安全区")
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        paragraph_lines = []
        line = ""
        for character in paragraph:
            candidate = line + character
            if draw.textlength(candidate, font=font) <= width:
                line = candidate
                continue
            if not line:
                raise ValueError("字幕超出文字安全区")
            if character in _LINE_START_FORBIDDEN and len(line) > 1:
                previous = line[-1]
                prefix = line[:-1]
                joined = previous + character
                if (
                    draw.textlength(prefix, font=font) <= width
                    and draw.textlength(joined, font=font) <= width
                ):
                    paragraph_lines.append(prefix)
                    line = joined
                    continue
            if line[-1] in _LINE_END_FORBIDDEN and len(line) > 1:
                opening = line[-1]
                prefix = line[:-1]
                joined = opening + character
                if (
                    draw.textlength(prefix, font=font) <= width
                    and draw.textlength(joined, font=font) <= width
                ):
                    paragraph_lines.append(prefix)
                    line = joined
                    continue
            paragraph_lines.append(line)
            line = character
        paragraph_lines.append(line)
        for index in range(1, len(paragraph_lines)):
            current = paragraph_lines[index]
            if not current or current[0] not in _LINE_START_FORBIDDEN:
                continue
            previous = paragraph_lines[index - 1]
            if not previous:
                continue
            moved = previous[-1]
            prefix = previous[:-1]
            joined = moved + current
            if (
                prefix
                and draw.textlength(prefix, font=font) <= width
                and draw.textlength(joined, font=font) <= width
            ):
                paragraph_lines[index - 1] = prefix
                paragraph_lines[index] = joined
            elif draw.textlength(previous + current, font=font) <= width:
                paragraph_lines[index - 1] = previous + current
                paragraph_lines[index] = ""
        lines.extend(paragraph_lines)
    return lines


def _areas_overlap(first, second):
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    return (
        first_x < second_x + second_width
        and second_x < first_x + first_width
        and first_y < second_y + second_height
        and second_y < first_y + first_height
    )


def select_text_safe_area(social_layout):
    """Select the first declared text area that does not overlap the subject area."""
    candidates = social_layout.get("text_safe_area_candidates") or [
        social_layout.get("text_safe_area")
    ]
    subject_area = social_layout.get("subject_safe_area")
    for area in candidates:
        if (
            not isinstance(area, list)
            or len(area) != 4
            or not all(isinstance(item, (int, float)) for item in area)
        ):
            continue
        if subject_area and _areas_overlap(area, subject_area):
            continue
        return area
    raise ValueError("没有可用的文字安全区")


def fit_text_layout(
    text,
    draw,
    font_path,
    content_box,
    requested_size=54,
    minimum_size=SOCIAL_MIN_FONT_SIZE,
    max_lines=8,
):
    """Fit copy into a measured pixel box without silently dropping text."""
    _, _, width, height = content_box
    if width <= 0 or height <= 0:
        raise ValueError("字幕超出文字安全区")
    requested_size = round(requested_size)
    minimum_size = round(minimum_size)
    if requested_size <= 0 or minimum_size <= 0 or minimum_size > requested_size:
        raise ValueError("社媒字号范围无效")
    for font_size in range(requested_size, minimum_size - 1, -1):
        font = ImageFont.truetype(str(font_path), font_size)
        lines = _wrap_text(text, draw, font, width) if text else []
        if len(lines) > max_lines:
            continue
        ascent, descent = font.getmetrics()
        font_height = ascent + descent
        leading = max(round(font_size * 1.25), font_height)
        text_height = (len(lines) - 1) * leading + font_height if lines else 0
        text_width = max(
            (draw.textlength(line, font=font) for line in lines), default=0
        )
        if text_height <= height:
            return {
                "font": font,
                "font_size": font_size,
                "font_height": font_height,
                "leading": leading,
                "lines": lines,
                "text_height": text_height,
                "text_width": text_width,
            }
    raise ValueError("字幕超出文字安全区")


def text_density_warnings(text, lines, age_band):
    """Return advisory density warnings; this function never changes copy."""
    normalized_age_band = str(age_band or "").replace("—", "-").replace("–", "-")
    if normalized_age_band != "3-4":
        return []
    character_count = len(text.replace("\n", ""))
    warnings = []
    if character_count >= 40:
        warnings.append("正文较长")
    if len(lines) >= 7:
        warnings.append("行数较多")
    if text.count("“") >= 2 or text.count('"') >= 2:
        warnings.append("对话较长")
    return warnings


def render_social_page(
    page, output_path, profile=_PROFILE_OMITTED, layout_info=None
) -> Path:
    """Render a profile-sized PNG/JPEG, reusing the page profile when omitted."""
    if not isinstance(page, dict):
        raise ValueError("社媒页面必须是对象")

    layout_design = page.get("layout_design")
    errors = validate_layout_design(layout_design, require_complete=True)
    if errors:
        raise ValueError("; ".join(errors))
    social_layout = layout_design["social_layout"]
    profile_was_omitted = profile is _PROFILE_OMITTED
    if profile_was_omitted:
        profile = social_layout["profile"]
    elif social_layout["profile"] != profile:
        raise ValueError("社媒profile与layout_design不一致")
    profile_config = get_social_profile(profile)
    if profile_config is None:
        raise ValueError("不支持的社媒profile")

    output_path = Path(output_path)
    if output_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("社媒输出必须是PNG或JPEG")
    if output_path.exists():
        raise FileExistsError(output_path)

    image_value = page.get("image_path")
    if not image_value:
        raise ValueError("社媒页面缺少image_path")
    image_path = Path(image_value)
    if not image_path.is_file():
        raise ValueError("社媒源图不存在")

    canvas = profile_config["canvas"]
    width = canvas["width_px"]
    height = canvas["height_px"]
    with Image.open(image_path) as source:
        source.load()
        source_aspect_ratio = profile_config["source_aspect_ratio"]
        if not image_matches_aspect_ratio(
            source.width, source.height, source_aspect_ratio
        ):
            raise ValueError(
                f"社媒源图必须是{source_aspect_ratio}，不能默认中心裁切印刷页"
            )
        rendered = source.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)

    text = page.get("text", "")
    if not isinstance(text, str):
        raise ValueError("社媒正文必须是字符串")
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    style = resolve_text_style(layout_design)
    text_area = select_text_safe_area(social_layout)
    text_box = _pixel_box(text_area, width, height)
    draw = ImageDraw.Draw(rendered)

    font_size = page.get("social_font_size", 54)
    if type(font_size) not in (int, float) or not math.isfinite(font_size) or font_size <= 0:
        raise ValueError("社媒字号必须是正数")
    font_value = page.get("font_path")
    font_path = Path(font_value) if font_value else Path(__file__).resolve().parents[1] / "assets" / "kidsbook-print.ttf"
    if not font_path.is_file():
        raise ValueError("社媒字体路径不可用")
    padding = SOCIAL_TEXT_PADDING_PX if style.draws_panel else 0
    content_box = (
        text_box[0] + padding,
        text_box[1] + padding,
        text_box[2] - text_box[0] - 2 * padding,
        text_box[3] - text_box[1] - 2 * padding,
    )
    layout = fit_text_layout(
        text,
        draw,
        font_path,
        content_box,
        requested_size=font_size,
        minimum_size=page.get("social_min_font_size", SOCIAL_MIN_FONT_SIZE),
        max_lines=layout_design["max_lines"],
    )
    font = layout["font"]
    lines = layout["lines"]
    leading = layout["leading"]
    actual_width = layout["text_width"] + 2 * padding
    actual_height = layout["text_height"] + 2 * padding
    if style.text_align == "center":
        actual_x = text_box[0] + max(0, (text_box[2] - text_box[0] - actual_width) / 2)
    else:
        actual_x = text_box[0]
    actual_y = text_box[1]
    actual_box = (actual_x, actual_y, actual_width, actual_height)

    if style.draws_panel:
        radius = SOCIAL_CARD_RADIUS_PX if style.mode == "soft-card" else SOCIAL_BAND_RADIUS_PX
        draw.rounded_rectangle(
            (
                round(actual_box[0]),
                round(actual_box[1]),
                round(actual_box[0] + actual_box[2]),
                round(actual_box[1] + actual_box[3]),
            ),
            radius=radius,
            fill=style.panel_rgb,
        )
    x = actual_box[0] + padding
    y = actual_box[1] + padding
    for index, line in enumerate(lines):
        if style.text_align == "center":
            line_width = draw.textlength(line, font=font)
            line_x = x + (content_width - line_width) / 2
        else:
            line_x = x
        if style.mode == "scene-integrated":
            # A local halo preserves the illustration while keeping copy readable
            # on mildly textured backgrounds; it is not a page-wide text panel.
            halo_width = max(1, round(font_size * 0.05))
            draw.text(
                (line_x, y + index * leading),
                line,
                font=font,
                fill=style.text_rgb,
                stroke_width=halo_width,
                stroke_fill=style.panel_rgb,
            )
        else:
            draw.text((line_x, y + index * leading), line, font=font, fill=style.text_rgb)

    if layout_info is not None:
        layout_info.update(
            {
                "text_area": list(text_area),
                "pixel_box": [round(value) for value in actual_box],
                "font_size": layout["font_size"],
                "line_count": len(lines),
                "lines": list(lines),
                "text_height": layout["text_height"],
                "text_width": round(layout["text_width"]),
                "minimum_font_size": round(page.get("social_min_font_size", SOCIAL_MIN_FONT_SIZE)),
                "density_warnings": text_density_warnings(
                    text, lines, page.get("age_band")
                ),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary = tempfile.mkstemp(suffix=output_path.suffix, dir=output_path.parent)
    os.close(file_descriptor)
    try:
        save_options = {"quality": 95} if output_path.suffix.lower() in {".jpg", ".jpeg"} else {}
        rendered.save(temporary, **save_options)
        os.link(temporary, output_path)
    finally:
        rendered.close()
        if os.path.exists(temporary):
            os.unlink(temporary)
    return output_path

"""Fixed, opaque print styles for layered picturebook text."""

from dataclasses import dataclass

from reportlab.pdfbase import pdfmetrics

from layout_design import LAYOUT_MODE_TO_TREATMENT, PALETTE_TOKENS


MM = 72 / 25.4


@dataclass(frozen=True)
class TextBlockStyle:
    mode: str
    text_rgb: tuple[int, int, int]
    panel_rgb: tuple[int, int, int]
    padding_pt: float
    corner_radius_pt: float
    text_align: str
    draws_panel: bool


PRINT_PALETTES = {
    "warm-paper": {"text_rgb": (63, 51, 43), "panel_rgb": (246, 235, 217)},
    "cool-sky": {"text_rgb": (36, 58, 74), "panel_rgb": (230, 241, 245)},
    "soft-leaf": {"text_rgb": (49, 70, 58), "panel_rgb": (231, 240, 228)},
}

if set(PRINT_PALETTES) != PALETTE_TOKENS:
    raise RuntimeError("打印调色板必须与layout_design公开令牌一致")


_STYLE_GEOMETRY = {
    "scene-integrated": {"padding_pt": 0.0, "corner_radius_pt": 0.0, "draws_panel": False},
    "soft-card": {"padding_pt": 4 * MM, "corner_radius_pt": 3 * MM, "draws_panel": True},
    "narrative-band": {"padding_pt": 4 * MM, "corner_radius_pt": 1.5 * MM, "draws_panel": True},
}

SOCIAL_TEXT_PADDING_PX = 32
SOCIAL_CARD_RADIUS_PX = 28
SOCIAL_BAND_RADIUS_PX = 12


def resolve_text_style(layout_design: dict) -> TextBlockStyle:
    """Resolve validated layout data to one immutable drawing style."""
    if not isinstance(layout_design, dict):
        raise ValueError("layout_design必须是对象")
    mode = layout_design.get("layout_mode")
    if mode not in LAYOUT_MODE_TO_TREATMENT:
        raise ValueError("layout_mode必须是受支持的版式模式")
    palette_token = layout_design.get("palette_token")
    if palette_token not in PALETTE_TOKENS:
        raise ValueError("palette_token必须是受支持的调色板令牌")
    palette = PRINT_PALETTES[palette_token]
    geometry = _STYLE_GEOMETRY[mode]
    return TextBlockStyle(
        mode=mode,
        text_rgb=palette["text_rgb"],
        panel_rgb=palette["panel_rgb"],
        padding_pt=geometry["padding_pt"],
        corner_radius_pt=geometry["corner_radius_pt"],
        text_align=layout_design.get("text_align", "left"),
        draws_panel=geometry["draws_panel"],
    )


def text_content_box(box_pt, style: TextBlockStyle):
    """Return the inset box used by wrapping, overflow checks, and drawing."""
    x, y, width, height = box_pt
    padding = style.padding_pt
    inner = (x + padding, y + padding, width - 2 * padding, height - 2 * padding)
    if inner[2] <= 0 or inner[3] <= 0:
        raise ValueError("文字框无法容纳固定内边距")
    return inner


def draw_text_block(canvas, lines, box_pt, font_name, font_size, leading, style) -> None:
    """Draw an optional opaque panel and an extractable PDF text layer."""
    x, y, width, height = box_pt
    canvas.saveState()
    try:
        if style.draws_panel:
            canvas.setFillColorRGB(*(channel / 255 for channel in style.panel_rgb))
            canvas.roundRect(
                x,
                y,
                width,
                height,
                style.corner_radius_pt,
                stroke=0,
                fill=1,
            )

        inner_x, inner_y, inner_width, inner_height = text_content_box(box_pt, style)
        ascent, _ = pdfmetrics.getAscentDescent(font_name, font_size)
        canvas.setFillColorRGB(*(channel / 255 for channel in style.text_rgb))
        canvas.setFont(font_name, font_size)
        for index, line in enumerate(lines):
            baseline = inner_y + inner_height - ascent - index * leading
            if style.text_align == "center":
                canvas.drawCentredString(inner_x + inner_width / 2, baseline, line)
            else:
                canvas.drawString(inner_x, baseline, line)
    finally:
        canvas.restoreState()

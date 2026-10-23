import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from layout_styles import resolve_text_style
from render_book import render_book


FONT = str(ROOT / "assets" / "kidsbook-print.ttf")
MM = 72 / 25.4


def valid_layout_design(mode="scene-integrated", palette="warm-paper"):
    treatment = {
        "scene-integrated": "natural-space",
        "soft-card": "soft-card",
        "narrative-band": "narrative-band",
    }[mode]
    return {
        "layout_style_version": "layout-v1",
        "layout_mode": mode,
        "text_anchor": "top-left",
        "text_treatment": treatment,
        "text_align": "left",
        "max_lines": 4,
        "focal_point": "孩子手中的纸飞机",
        "text_safe_area": "左上方浅色墙面",
        "avoid_covering": ["人物脸部", "纸飞机"],
        "page_rhythm": "action",
        "palette_token": palette,
        "status": "passed",
        "social_layout": {
            "profile": "social-vertical-9x16",
            "canvas": {"width_px": 1080, "height_px": 1920},
            "subject_safe_area": [0.08, 0.10, 0.84, 0.62],
            "text_safe_area": [0.08, 0.76, 0.84, 0.14],
            "avoid_regions": ["top-ui", "bottom-ui"],
            "source_aspect_ratio": "9:16",
            "status": "passed",
        },
    }


class LayoutStyleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def render(self, mode, palette="warm-paper", text="小朋友造桥。", box=None):
        data = {
            "font_path": FONT,
            "page_mm": [148, 210],
            "font_size": 22,
            "target_dpi": 300,
            "safe_margin_mm": 10,
            "pages": [
                {
                    "number": 1,
                    "text": text,
                    "image": None,
                    "text_box_mm": box or [14, 20, 120, 40],
                    "layout_design": valid_layout_design(mode, palette),
                }
            ],
        }
        manifest = self.root / f"{mode}.json"
        output = self.root / f"{mode}.pdf"
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        render_book(manifest, output)
        return output

    def panel_pixel(self, output):
        document = fitz.open(output)
        page = document[0]
        pixmap = page.get_pixmap(alpha=False)
        x = round(20 * MM)
        y = round(page.rect.height - 24 * MM)
        pixel = pixmap.pixel(x, y)
        document.close()
        return pixel

    def assert_pdf_contract(self, output):
        reader = PdfReader(output)
        page = reader.pages[0]
        self.assertIn("小朋友造桥。", page.extract_text())
        self.assertAlmostEqual(float(page.mediabox.width), 148 * MM, places=3)
        self.assertAlmostEqual(float(page.mediabox.height), 210 * MM, places=3)
        fonts = page["/Resources"]["/Font"]
        self.assertTrue(
            any(
                font.get_object().get("/FontDescriptor", {}).get("/FontFile2")
                for font in fonts.values()
            )
        )

    def test_scene_integrated_keeps_text_extractable_without_panel(self):
        output = self.render("scene-integrated")

        self.assert_pdf_contract(output)
        self.assertEqual((255, 255, 255), self.panel_pixel(output))

    def test_soft_card_renders_panel_and_extractable_text(self):
        output = self.render("soft-card", "cool-sky")

        self.assert_pdf_contract(output)
        self.assertNotEqual((255, 255, 255), self.panel_pixel(output))

    def test_narrative_band_renders_panel_and_extractable_text(self):
        output = self.render("narrative-band", "soft-leaf")

        self.assert_pdf_contract(output)
        self.assertNotEqual((255, 255, 255), self.panel_pixel(output))

    def test_invalid_palette_token_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "palette_token必须是受支持的调色板令牌"):
            self.render("soft-card", "neon")

    def test_soft_card_padding_still_fits_inside_safe_box(self):
        output = self.render("soft-card")
        positions = []
        PdfReader(output).pages[0].extract_text(
            visitor_text=lambda text, cm, tm, font, size: positions.append((tm[4], tm[5]))
            if text.strip()
            else None
        )
        style = resolve_text_style(valid_layout_design("soft-card"))
        x, baseline = positions[0]
        outer_x, outer_y, outer_width, outer_height = (value * MM for value in [14, 20, 120, 40])

        self.assertAlmostEqual(x, outer_x + style.padding_pt, places=3)
        self.assertGreaterEqual(baseline, outer_y + style.padding_pt)
        self.assertLessEqual(x, outer_x + outer_width - style.padding_pt)
        self.assertLessEqual(baseline, outer_y + outer_height - style.padding_pt)


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_social_book import render_social_book


def layout_design(mode="scene-integrated"):
    return {
        "layout_style_version": "layout-v1",
        "layout_mode": mode,
        "text_anchor": "top-left",
        "text_treatment": "natural-space" if mode == "scene-integrated" else "soft-card",
        "text_align": "left",
        "max_lines": 6,
        "focal_point": "两个孩子在阅读角一起看花环",
        "text_safe_area": "右上方浅色墙面",
        "avoid_covering": ["孩子的脸和手"],
        "page_rhythm": "action",
        "palette_token": "warm-paper",
        "status": "passed",
        "social_layout": {
            "profile": "xiaohongshu-feed-3x4",
            "canvas": {"width_px": 1080, "height_px": 1440},
            "subject_safe_area": [0.06, 0.42, 0.88, 0.52],
            "text_safe_area": [0.56, 0.06, 0.38, 0.30],
            "composition_mode": "portrait-full-bleed",
            "text_placement": "in-scene",
            "avoid_regions": ["孩子的脸和手"],
            "source_aspect_ratio": "3:4",
            "status": "passed",
        },
    }


class SocialOnlyOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.font = Path(__file__).resolve().parents[1] / "assets" / "kidsbook-print.ttf"
        for number in (1, 2):
            Image.new("RGB", (1086, 1448), (241, 226, 201)).save(
                self.root / f"page-{number:02d}.png"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def write_layout(self, mode="scene-integrated"):
        pages = []
        for number in (1, 2):
            pages.append(
                {
                    "number": number,
                    "text": "小熊和小猛一起做花环。",
                    "image": f"page-{number:02d}.png",
                    "image_path": f"page-{number:02d}.png",
                    "font_path": str(self.font),
                    "social_font_size": 42,
                    "layout_design": layout_design(mode),
                }
            )
        path = self.root / "layout.json"
        path.write_text(
            json.dumps({"output_mode": "social-only", "pages": pages}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_outputs_only_one_xiaohongshu_profile(self):
        output = self.root / "social"
        manifest = render_social_book(self.write_layout(), output)
        self.assertEqual(manifest["profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(manifest["canvas"], {"width_px": 1080, "height_px": 1440})
        self.assertEqual(sorted(p.name for p in output.glob("*.png")), ["page-01.png", "page-02.png"])
        self.assertFalse((output / "reading.pdf").exists())
        self.assertFalse((output / "print.pdf").exists())

    def test_rejects_legacy_card_layout_in_social_only_mode(self):
        with self.assertRaisesRegex(ValueError, "scene-integrated"):
            render_social_book(self.write_layout("soft-card"), self.root / "social")


if __name__ == "__main__":
    unittest.main()

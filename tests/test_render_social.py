import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render_social
from render_social import render_social_page


def valid_layout_design(profile="xiaohongshu-feed-3x4"):
    if profile == "xiaohongshu-feed-3x4":
        canvas = {"width_px": 1080, "height_px": 1440}
        source_aspect_ratio = "3:4"
        layout_mode = "scene-integrated"
        text_anchor = "top-left"
        text_treatment = "natural-space"
        layout_text_safe_area = "画面左上方的浅色墙面"
        subject_safe_area = [0.50, 0.20, 0.42, 0.54]
        social_text_safe_area = [0.08, 0.12, 0.38, 0.24]
        social_contract = {
            "composition_mode": "portrait-full-bleed",
            "text_placement": "in-scene",
        }
    else:
        canvas = {"width_px": 1080, "height_px": 1920}
        source_aspect_ratio = "9:16"
        layout_mode = "soft-card"
        text_anchor = "bottom-left"
        text_treatment = "soft-card"
        layout_text_safe_area = "画面下方的浅色地面"
        subject_safe_area = [0.08, 0.10, 0.84, 0.62]
        social_text_safe_area = [0.08, 0.76, 0.84, 0.14]
        social_contract = {}
    return {
        "layout_style_version": "layout-v1",
        "layout_mode": layout_mode,
        "text_anchor": text_anchor,
        "text_treatment": text_treatment,
        "text_align": "left",
        "max_lines": 4,
        "focal_point": "孩子手中的纸飞机",
        "text_safe_area": layout_text_safe_area,
        "avoid_covering": ["人物脸部", "纸飞机"],
        "page_rhythm": "action",
        "palette_token": "warm-paper",
        "status": "passed",
        "social_layout": {
            "profile": profile,
            "canvas": canvas,
            "subject_safe_area": subject_safe_area,
            "text_safe_area": social_text_safe_area,
            "avoid_regions": ["top-ui", "bottom-ui"],
            "source_aspect_ratio": source_aspect_ratio,
            "status": "passed",
            **social_contract,
        },
    }


class SocialRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "social-source.png"
        Image.new("RGB", (900, 1200), (120, 160, 200)).save(self.source)
        self.page = {
            "image_path": self.source,
            "text": "小朋友一起造桥。",
            "font_path": ROOT / "assets" / "kidsbook-print.ttf",
            "layout_design": valid_layout_design(),
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_social_renderer_defaults_to_xiaohongshu_feed_size(self):
        output = render_social_page(self.page, self.root / "page-01.png")

        self.assertEqual(self.root / "page-01.png", output)
        with Image.open(output) as rendered:
            self.assertEqual((1080, 1440), rendered.size)

    def test_social_renderer_accepts_typical_in_scene_copy(self):
        self.page["text"] = "小朋友发现：画面里的文字可以和故事一起阅读。"

        output = render_social_page(self.page, self.root / "typical-copy-page-01.png")

        with Image.open(output) as rendered:
            self.assertEqual((1080, 1440), rendered.size)

    def test_social_renderer_requires_in_scene_layout_contract(self):
        self.page["layout_design"]["social_layout"].pop("composition_mode")
        self.page["layout_design"]["social_layout"].pop("text_placement")
        with self.assertRaisesRegex(
            ValueError,
            "完成模式要求social_layout.composition_mode为portrait-full-bleed",
        ):
            render_social_page(self.page, self.root / "page-01.png")

    def test_social_renderer_rejects_non_3x4_source(self):
        Image.new("RGB", (1200, 1200), "white").save(self.source)

        with self.assertRaisesRegex(ValueError, "源图必须是3:4"):
            render_social_page(self.page, self.root / "page-01.png")

    def test_social_renderer_explicit_9x16_preserves_legacy_output(self):
        self.page["layout_design"] = valid_layout_design("social-vertical-9x16")
        Image.new("RGB", (900, 1600), (120, 160, 200)).save(self.source)

        output = render_social_page(
            self.page,
            self.root / "legacy-page-01.png",
            profile="social-vertical-9x16",
        )

        with Image.open(output) as rendered:
            self.assertEqual((1080, 1920), rendered.size)

    def test_social_renderer_omitted_profile_reuses_legacy_9x16_layout(self):
        self.page["layout_design"] = valid_layout_design("social-vertical-9x16")
        Image.new("RGB", (900, 1600), (120, 160, 200)).save(self.source)

        output = render_social_page(self.page, self.root / "legacy-default-page-01.png")

        with Image.open(output) as rendered:
            self.assertEqual((1080, 1920), rendered.size)

    def test_social_renderer_explicit_profile_mismatch_is_rejected(self):
        self.page["layout_design"] = valid_layout_design("social-vertical-9x16")
        Image.new("RGB", (900, 1600), (120, 160, 200)).save(self.source)

        with self.assertRaisesRegex(ValueError, "社媒profile与layout_design不一致"):
            render_social_page(
                self.page,
                self.root / "mismatched-profile-page-01.png",
                profile="xiaohongshu-feed-3x4",
            )

    def test_social_renderer_explicit_9x16_rejects_3x4_source(self):
        self.page["layout_design"] = valid_layout_design("social-vertical-9x16")
        Image.new("RGB", (900, 1200), (120, 160, 200)).save(self.source)

        with self.assertRaisesRegex(ValueError, "源图必须是9:16"):
            render_social_page(
                self.page,
                self.root / "wrong-source-page-01.png",
                profile="social-vertical-9x16",
            )

    def test_social_renderer_rejects_text_outside_safe_area(self):
        self.page["layout_design"]["social_layout"]["text_safe_area"] = [0.08, 0.12, 0.38, 0.005]
        self.page["text"] = "这是一段无法放入过小字幕安全区的文字。"

        with self.assertRaisesRegex(ValueError, "字幕超出文字安全区"):
            render_social_page(self.page, self.root / "page-01.png")

    def test_cjk_wrap_keeps_punctuation_with_adjacent_text(self):
        image = Image.new("RGB", (1080, 1440), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(ROOT / "assets" / "kidsbook-print.ttf"), 44)
        lines = render_social._wrap_text("妈妈说：“冰就是冻住的水。”小熊点点头。", draw, font, 280)

        self.assertGreater(len(lines), 1)
        self.assertTrue(all(draw.textlength(line, font=font) <= 280 for line in lines))
        self.assertTrue(all(line and line[0] not in "，。！？：；、”’）》】》…" for line in lines))
        self.assertFalse(any(line in "，。！？：；、”’）》】》…" for line in lines))

    def test_fit_text_layout_uses_measured_height_and_reduces_size_within_limit(self):
        image = Image.new("RGB", (1080, 1440), "white")
        draw = ImageDraw.Draw(image)
        self.assertTrue(hasattr(render_social, "fit_text_layout"))
        result = render_social.fit_text_layout(
            "妈妈指着杯子说：“冰就是冻住的水。周围比冰暖和时，冰会慢慢融化，又变成水。”",
            draw,
            ROOT / "assets" / "kidsbook-print.ttf",
            (64, 70, 430, 300),
            requested_size=54,
            minimum_size=36,
            max_lines=8,
        )

        self.assertLess(result["font_size"], 54)
        self.assertLessEqual(result["text_height"], 300)
        self.assertEqual(result["text_height"], result["leading"] * (len(result["lines"]) - 1) + result["font_height"])

    def test_text_safe_area_candidates_skip_subject_overlap(self):
        self.assertTrue(hasattr(render_social, "select_text_safe_area"))
        selected = render_social.select_text_safe_area(
            {
                "text_safe_area": [0.05, 0.04, 0.35, 0.20],
                "text_safe_area_candidates": [
                    [0.05, 0.04, 0.35, 0.20],
                    [0.60, 0.04, 0.32, 0.20],
                ],
                "subject_safe_area": [0.20, 0.02, 0.30, 0.80],
            }
        )

        self.assertEqual([0.60, 0.04, 0.32, 0.20], selected)

    def test_text_safe_area_candidates_raise_when_all_overlap_subject(self):
        with self.assertRaisesRegex(ValueError, "没有可用的文字安全区"):
            self.assertTrue(hasattr(render_social, "select_text_safe_area"))
            render_social.select_text_safe_area(
                {
                    "text_safe_area": [0.05, 0.04, 0.35, 0.20],
                    "text_safe_area_candidates": [
                        [0.05, 0.04, 0.35, 0.20],
                        [0.60, 0.04, 0.32, 0.20],
                    ],
                    "subject_safe_area": [0.00, 0.00, 1.00, 1.00],
                }
            )

    def test_age_band_density_check_reports_without_rewriting_copy(self):
        text = "妈妈指着杯子说：“冰就是冻住的水。周围比冰暖和时，冰会慢慢融化，又变成水。”小熊和小猛一起点点头。"
        warnings = render_social.text_density_warnings(text, ["一"] * 7, "3-4")

        self.assertIn("正文较长", warnings)
        self.assertIn("行数较多", warnings)


if __name__ == "__main__":
    unittest.main()

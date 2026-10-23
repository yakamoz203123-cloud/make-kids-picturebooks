import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from accept_social_book import accept_social_book  # noqa: E402
from render_social_book import render_social_book  # noqa: E402


class SocialAcceptanceTests(unittest.TestCase):
    def test_accepts_only_reviewed_social_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            for number in (1, 2):
                Image.new("RGB", (1086, 1448), (248, 238, 214)).save(
                    images / f"page-{number:02d}.png"
                )
            layout = {
                "output_mode": "social-only",
                "font_path": str(ROOT / "assets" / "kidsbook-print.ttf"),
                "pages": [
                    {
                        "number": number,
                        "text": f"第{number}页文字。",
                        "image": f"images/page-{number:02d}.png",
                        "social_font_size": 32,
                        "layout_design": {
                            "layout_style_version": "layout-v1",
                            "layout_mode": "scene-integrated",
                            "text_anchor": "top-right",
                            "text_treatment": "natural-space",
                            "text_align": "left",
                            "max_lines": 4,
                            "focal_point": "测试人物",
                            "text_safe_area": "右上方浅色留白",
                            "avoid_covering": ["测试人物的脸"],
                            "page_rhythm": "action",
                            "palette_token": "warm-paper",
                            "status": "passed",
                            "social_layout": {
                                "profile": "xiaohongshu-feed-3x4",
                                "canvas": {"width_px": 1080, "height_px": 1440},
                                "composition_mode": "portrait-full-bleed",
                                "text_placement": "in-scene",
                                "subject_safe_area": [0.04, 0.45, 0.92, 0.5],
                                "text_safe_area": [0.56, 0.06, 0.38, 0.34],
                                "avoid_regions": ["top-ui", "bottom-ui"],
                                "source_aspect_ratio": "3:4",
                                "status": "passed",
                            },
                        },
                    }
                    for number in (1, 2)
                ],
            }
            layout_path = root / "layout.json"
            layout_path.write_text(json.dumps(layout, ensure_ascii=False), encoding="utf-8")
            output_dir = root / "social"
            render_social_book(layout_path, output_dir)
            review = {
                "output_mode": "social-only",
                "social_pages": [
                    {
                        "page": number,
                        "status": "passed",
                        "evidence": "已核对该页成品尺寸、人物与正文位置。",
                        "layout_review": {
                            "status": "passed",
                            "evidence": "文字位于画面内部自然留白，未遮挡主体。",
                            "text_image_relationship": "integrated",
                        },
                    }
                    for number in (1, 2)
                ],
                "contact_sheet_review": {
                    "status": "passed",
                    "evidence": "已查看整书缩略图总览。",
                },
                "engineering_evidence": {"status": "passed", "evidence": "文件已核对。"},
                "content_evidence": {"status": "passed", "evidence": "内容已核对。"},
                "visual_evidence": {"status": "passed", "evidence": "逐页已查看。"},
                "real_reading_evidence": {"status": "pending", "evidence": "尚未共读。"},
                "unresolved_digital_defects": [],
            }
            review_path = root / "review.json"
            review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            acceptance_path = root / "acceptance.json"

            result = accept_social_book(layout_path, output_dir, review_path, acceptance_path)

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["output_mode"], "social-only")
            self.assertEqual(result["page_count"], 2)
            self.assertTrue(acceptance_path.is_file())

    def test_rejects_missing_visual_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout_path = root / "layout.json"
            layout_path.write_text('{"output_mode":"social-only","pages":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pages列表"):
                accept_social_book(layout_path, root / "social", root / "review.json", root / "acceptance.json")


if __name__ == "__main__":
    unittest.main()

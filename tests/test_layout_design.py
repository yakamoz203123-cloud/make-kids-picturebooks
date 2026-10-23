import sys
from pathlib import Path
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from layout_design import validate_layout_design, validate_layout_review


def valid_social_layout():
    return {
        "profile": "social-vertical-9x16",
        "canvas": {"width_px": 1080, "height_px": 1920},
        "subject_safe_area": [0.08, 0.10, 0.84, 0.62],
        "text_safe_area": [0.08, 0.76, 0.84, 0.14],
        "avoid_regions": ["top-ui", "bottom-ui"],
        "source_aspect_ratio": "9:16",
        "status": "passed",
    }


def valid_xiaohongshu_social_layout():
    layout = valid_social_layout()
    layout.update(
        {
            "profile": "xiaohongshu-feed-3x4",
            "canvas": {"width_px": 1080, "height_px": 1440},
            "subject_safe_area": [0.50, 0.20, 0.42, 0.54],
            "text_safe_area": [0.08, 0.12, 0.38, 0.24],
            "composition_mode": "portrait-full-bleed",
            "text_placement": "in-scene",
            "source_aspect_ratio": "3:4",
        }
    )
    return layout


def valid_layout_design():
    return {
        "layout_style_version": "layout-v1",
        "layout_mode": "scene-integrated",
        "text_anchor": "top-left",
        "text_treatment": "natural-space",
        "text_align": "left",
        "max_lines": 4,
        "focal_point": "孩子手中的纸飞机",
        "text_safe_area": "左上方浅色墙面",
        "avoid_covering": ["人物脸部", "手部动作", "纸飞机"],
        "page_rhythm": "action",
        "palette_token": "warm-paper",
        "status": "passed",
        "social_layout": valid_social_layout(),
    }


def valid_layout_review():
    return {
        "status": "passed",
        "evidence": "正文位于左上方浅色墙面，未遮挡两名儿童的脸和纸飞机。",
        "text_image_relationship": "integrated",
        "contrast": "passed",
        "focal_point_clear": True,
        "occlusion": "none",
        "rhythm_reason": "动作页以右下人物和左上文字承接上一页视线。",
    }


class LayoutDesignTests(unittest.TestCase):
    def test_planning_allows_missing_layout_design(self):
        self.assertEqual([], validate_layout_design(None))

    def test_completion_requires_layout_design(self):
        self.assertEqual(["完成模式需要layout_design"], validate_layout_design(None, True))

    def test_rejects_unknown_layout_mode(self):
        design = valid_layout_design()
        design["layout_mode"] = "floating-caption"

        self.assertIn("layout_mode必须是受支持的版式模式", validate_layout_design(design, True))

    def test_rejects_mismatched_layout_mode_and_text_treatment(self):
        design = valid_layout_design()
        design["text_treatment"] = "soft-card"

        self.assertIn("layout_mode与text_treatment必须匹配", validate_layout_design(design, True))

    def test_rejects_nonpositive_max_lines(self):
        design = valid_layout_design()
        design["max_lines"] = 0

        self.assertIn("max_lines必须是正整数", validate_layout_design(design, True))

    def test_rejects_empty_avoid_covering_without_reason(self):
        for reason in (None, "   "):
            with self.subTest(reason=reason):
                design = valid_layout_design()
                design["avoid_covering"] = []
                if reason is not None:
                    design["avoid_covering_reason"] = reason

                self.assertIn(
                    "avoid_covering为空时必须提供avoid_covering_reason",
                    validate_layout_design(design, True),
                )

    def test_accepts_empty_avoid_covering_with_reason(self):
        design = valid_layout_design()
        design["avoid_covering"] = []
        design["avoid_covering_reason"] = "纯风景页，没有人物或知识关键物"

        self.assertEqual([], validate_layout_design(design, True))

    def test_planning_allows_empty_avoid_covering_without_reason(self):
        design = valid_layout_design()
        design["avoid_covering"] = []

        self.assertEqual([], validate_layout_design(design))

    def test_requires_specific_focal_point_and_safe_area_on_completion(self):
        design = valid_layout_design()
        design["focal_point"] = "主体"
        design["text_safe_area"] = ""

        errors = validate_layout_design(design, True)

        self.assertIn("focal_point必须描述具体画面对象或动作", errors)
        self.assertIn("text_safe_area必须描述实际画面文字区域", errors)

    def test_requires_complete_layout_review_on_completion(self):
        self.assertEqual(["完成模式需要layout_review"], validate_layout_review(None, True))

    def test_rejects_generic_layout_review_evidence(self):
        review = valid_layout_review()
        review["evidence"] = "已检查，效果良好"

        self.assertIn("layout_review.evidence必须提供具体版式证据", validate_layout_review(review, True))

    def test_rejects_generic_short_layout_review_evidence(self):
        for evidence in ("通过了", "已审核通过", "检查过了", "没问题", "looks good"):
            with self.subTest(evidence=evidence):
                review = valid_layout_review()
                review["evidence"] = evidence

                self.assertIn(
                    "layout_review.evidence必须提供具体版式证据",
                    validate_layout_review(review, True),
                )

    def test_accepts_concrete_short_layout_review_evidence(self):
        review = valid_layout_review()
        review["evidence"] = "左上文字未遮挡脸部"

        self.assertEqual([], validate_layout_review(review, True))

    def test_accepts_valid_social_layout(self):
        self.assertEqual([], validate_layout_design(valid_layout_design(), True))

    def test_accepts_xiaohongshu_social_layout(self):
        design = valid_layout_design()
        design["social_layout"] = valid_xiaohongshu_social_layout()

        self.assertEqual([], validate_layout_design(design, True))

    def test_xiaohongshu_requires_portrait_full_bleed_and_in_scene_text(self):
        design = valid_layout_design()
        design["social_layout"] = valid_xiaohongshu_social_layout()
        design["social_layout"].pop("composition_mode")
        design["social_layout"].pop("text_placement")

        errors = validate_layout_design(design, True)

        self.assertIn(
            "完成模式要求social_layout.composition_mode为portrait-full-bleed",
            errors,
        )
        self.assertIn(
            "完成模式要求social_layout.text_placement为in-scene",
            errors,
        )

    def test_xiaohongshu_rejects_bottom_text_strip(self):
        design = valid_layout_design()
        design["social_layout"] = valid_xiaohongshu_social_layout()
        design["social_layout"].update(
            {
                "text_safe_area": [0.08, 0.76, 0.84, 0.14],
            }
        )

        errors = validate_layout_design(design, True)

        self.assertIn(
            "social_layout.text_safe_area不得是底部通栏",
            errors,
        )

    def test_rejects_overlapping_social_safe_areas(self):
        design = valid_layout_design()
        design["social_layout"]["subject_safe_area"] = [0.08, 0.10, 0.84, 0.72]

        errors = validate_layout_design(design, True)

        self.assertIn(
            "social_layout.subject_safe_area与text_safe_area不得重叠",
            errors,
        )

    def test_rejects_xiaohongshu_social_layout_with_wrong_canvas(self):
        design = valid_layout_design()
        design["social_layout"] = valid_xiaohongshu_social_layout()
        design["social_layout"]["canvas"] = {"width_px": 1080, "height_px": 1920}

        self.assertIn(
            "social_layout.canvas必须是1080×1440",
            validate_layout_design(design, True),
        )

    def test_rejects_xiaohongshu_social_layout_with_wrong_aspect_ratio(self):
        design = valid_layout_design()
        design["social_layout"] = valid_xiaohongshu_social_layout()
        design["social_layout"]["source_aspect_ratio"] = "9:16"

        self.assertIn(
            "social_layout.source_aspect_ratio必须是3:4",
            validate_layout_design(design, True),
        )

    def test_rejects_unknown_social_profile_with_stable_error(self):
        design = valid_layout_design()
        design["social_layout"]["profile"] = "unknown-social-profile"

        self.assertIn(
            "social_layout.profile必须是受支持的社媒profile",
            validate_layout_design(design, True),
        )

    def test_rejects_social_layout_out_of_bounds(self):
        design = valid_layout_design()
        design["social_layout"]["text_safe_area"] = [0.08, 0.90, 0.84, 0.14]

        self.assertIn(
            "social_layout.text_safe_area必须位于归一化画布范围内",
            validate_layout_design(design, True),
        )

    def test_rejects_social_layout_with_unrepresentable_coordinate(self):
        design = valid_layout_design()
        design["social_layout"]["subject_safe_area"] = [0, 0, 10**1000, 1]

        self.assertIn(
            "social_layout.subject_safe_area必须是四个归一化数值",
            validate_layout_design(design, True),
        )

    def test_rejects_social_layout_with_wrong_aspect_ratio(self):
        design = valid_layout_design()
        design["social_layout"]["source_aspect_ratio"] = "3:4"

        self.assertIn(
            "social_layout.source_aspect_ratio必须是9:16",
            validate_layout_design(design, True),
        )


if __name__ == "__main__":
    unittest.main()

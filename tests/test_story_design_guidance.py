from pathlib import Path
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (SKILL_DIR / relative_path).read_text(encoding="utf-8")


def read_optional(relative_path: str) -> str:
    path = SKILL_DIR / relative_path
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class StoryDesignGuidanceTests(unittest.TestCase):
    def test_story_design_reference_is_routed_before_storyboard(self) -> None:
        skill = read("SKILL.md")
        workflow = read("references/production-workflow.md")
        guidance = read_optional("references/story-design.md")

        self.assertIn("references/story-design.md", skill)
        self.assertIn("故事设计", workflow)
        self.assertIn("story-design.md", workflow)
        for term in (
            "story_promise",
            "protagonist_want",
            "why_now",
            "obstacle",
            "attempt",
            "feedback",
            "adjustment",
            "knowledge_tool",
            "emotional_payoff",
            "进入分镜前",
        ):
            with self.subTest(term=term):
                self.assertIn(term, guidance)

    def test_story_design_gate_rejects_lecture_like_stories(self) -> None:
        guidance = read_optional("references/story-design.md")

        for term in (
            "知识讲义化",
            "至少两次",
            "每轮反馈",
            "主角亲自",
            "情绪回报",
            "不得进入正式分镜",
        ):
            with self.subTest(term=term):
                self.assertIn(term, guidance)

    def test_continuation_without_story_gate_reenters_story_design(self) -> None:
        combined = read_optional("references/story-design.md") + read(
            "references/production-workflow.md"
        )

        for term in (
            "续做",
            "未取得故事门禁证据",
            "身份绕过",
            "先补做故事门禁",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)


if __name__ == "__main__":
    unittest.main()

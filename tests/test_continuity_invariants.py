from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(r"C:\Users\Windows\.codex\skills\make-kids-picturebooks")
SCRIPTS = SKILL_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from continuity_contract import (  # noqa: E402
    assemble_continuity_task,
    build_continuity_review_record,
    validate_continuity_invariants,
)
from generation_queue import init_queue  # noqa: E402
from page_versions import image_dependency_fingerprint  # noqa: E402
from page_production import assemble_page_task  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_invariants(reference_path: str = "references/page-01.png", reference_sha256: str | None = None) -> dict:
    record = {
        "schema_version": 1,
        "character": [
            {
                "character_id": "CHAR-GIRL-01",
                "fixed": {"outfit_id": "G-01", "hair": "双低马尾"},
                "required_action": "指向观察杯",
                "before_state": "种子完整",
                "current_state": "种皮出现小裂缝",
                "after_state": "等待下一页出现根",
            }
        ],
        "recurring_props": [
            {
                "prop_id": "PROP-OBS-CUP-01",
                "definition": {
                    "shape": "低矮、宽口、透明观察杯",
                    "ratio": "宽度明显大于高度",
                    "material": "透明",
                },
                "pages": [1, 2],
                "allowed_changes": ["viewpoint", "highlight"],
            }
        ],
        "scene_and_lighting": {
            "scene_id": "window-observation-table",
            "light_direction": "窗户左上方",
            "shadow_direction": "右下方",
            "shadow_foot_connection": True,
        },
        "science_stages": {
            "current_stage_id": "seed-crack",
            "stage_order": 3,
            "visible_parts": ["种皮小裂缝"],
            "not_yet_visible": ["明显的根", "嫩芽", "叶片"],
        },
    }
    if reference_sha256 is not None:
        record["reference_pages"] = [
            {
                "page": 1,
                "relation": "previous",
                "path": reference_path,
                "sha256": reference_sha256,
            }
        ]
    return record


def _page(number: int, *, invariants: dict | None = None, science_stage_id: str | None = None) -> dict:
    page = {"page": number, "page_id": f"PAGE-{number:02d}", "page_version": "v1"}
    if invariants is not None:
        page["continuity_invariants"] = invariants
    if science_stage_id is not None:
        page["science_stage_id"] = science_stage_id
    return page


class ContinuityInvariantTests(unittest.TestCase):
    def test_page_task_forwards_explicit_visual_direction_to_host(self):
        page = _page(1)
        direction = {
            "story_task": "把孩子的疑问变成一次可观察的尝试",
            "visual_subject": "小熊的手与墙上的手影",
            "must_show": ["手位于光源与白墙之间", "对应的暗手影"],
            "must_not_show": ["影子长出眼睛", "小猛代替小熊挡光"],
            "visual_result": "白墙上出现与手部轮廓对应的暗区",
            "science_evidence": "光源—遮挡物—承影面的顺序清楚",
            "composition_reason": "用侧面近景让三者关系一眼可读",
        }
        page["visual_direction"] = direction

        task = assemble_page_task(page, storyboard_page={"visual_direction": direction})

        self.assertEqual(task["visual_direction"], direction)

    def test_valid_contract_produces_binding_and_visual_reminders(self):
        result = validate_continuity_invariants(_page(1, invariants=_valid_invariants()))
        self.assertEqual(result["blocks"], [])
        self.assertTrue(result["binding"]["character"])
        self.assertTrue(result["warnings"])
        self.assertIn("低矮、宽口、透明观察杯", result["prompt_addendum"])

    def test_old_manifest_without_optional_contract_remains_valid(self):
        result = validate_continuity_invariants(_page(1))
        self.assertEqual(result["blocks"], [])
        self.assertEqual(result["warnings"], [])
        self.assertIsNone(result["binding"])

    def test_invalid_shape_is_block_not_visual_warning(self):
        invariants = _valid_invariants()
        invariants["recurring_props"] = {"prop_id": "bad"}
        result = validate_continuity_invariants(_page(1, invariants=invariants))
        self.assertTrue(any(item["code"] == "CONTINUITY_SCHEMA_INVALID" for item in result["blocks"]))

    def test_reference_path_escape_and_hash_mismatch_are_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inside = root / "references" / "page-01.png"
            inside.parent.mkdir()
            inside.write_bytes(b"reference")
            escaped = copy.deepcopy(_valid_invariants("../outside.png", "0" * 64))
            escaped["reference_pages"][0]["path"] = "../outside.png"
            result = validate_continuity_invariants(
                _page(1, invariants=escaped), project_root=root
            )
            codes = {item["code"] for item in result["blocks"]}
            self.assertIn("CONTINUITY_REFERENCE_PATH_ESCAPE", codes)
            self.assertNotIn("CONTINUITY_REFERENCE_HASH_MISMATCH", codes)

            bad_hash = _valid_invariants("references/page-01.png", "0" * 64)
            result = validate_continuity_invariants(
                _page(1, invariants=bad_hash), project_root=root
            )
            self.assertIn(
                "CONTINUITY_REFERENCE_HASH_MISMATCH",
                {item["code"] for item in result["blocks"]},
            )

    def test_explicit_science_stage_contradiction_is_blocked(self):
        invariants = _valid_invariants()
        result = validate_continuity_invariants(
            _page(1, invariants=invariants, science_stage_id="leaf-expanded"),
            storyboard_page={"science_stage_id": "leaf-expanded"},
        )
        # The invariant says seed-crack; the explicit storyboard stage disagrees.
        self.assertIn(
            "CONTINUITY_SCIENCE_STAGE_CONTRADICTION",
            {item["code"] for item in result["blocks"]},
        )

    def test_review_record_is_pre_post_evidence_and_not_approval(self):
        invariants = _valid_invariants()
        task = assemble_continuity_task(_page(1, invariants=invariants))
        record = build_continuity_review_record(
            _page(1, invariants=invariants),
            task,
            discovery_stage="post_generation",
            human_final_conclusion="pending",
            rework_needed="unknown",
        )
        for key in (
            "current_page",
            "constraints",
            "references",
            "structural_preflight",
            "human_visual_questions",
            "discovery_stage",
            "rework_needed",
            "human_final_conclusion",
        ):
            self.assertIn(key, record)
        self.assertEqual(record["human_final_conclusion"], "pending")
        self.assertNotEqual(record["structural_preflight"]["status"], "human_approved")

    def test_incomplete_science_stage_is_a_warning_not_a_fake_fact(self):
        invariants = {
            "schema_version": 1,
            "science_stages": {"visible_parts": ["裂缝"]},
        }
        result = validate_continuity_invariants(_page(1, invariants=invariants))
        self.assertEqual(result["blocks"], [])
        self.assertIn(
            "CONTINUITY_SCIENCE_STAGE_NOT_EXPLICIT",
            {item["code"] for item in result["warnings"]},
        )

    def test_declared_block_prevents_queue_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp) / "book"
            book.mkdir()
            (book / "prompts").mkdir()
            (book / "references").mkdir()
            (book / "story.md").write_text("offline", encoding="utf-8")
            (book / "prompts" / "page-01.md").write_text("prompt", encoding="utf-8")
            (book / "references" / "characters.png").write_bytes(b"characters")
            (book / "references" / "production.png").write_bytes(b"production")
            page = _page(1, invariants={"schema_version": 99})
            page.update({
                "text_version": "v1",
                "characters_version": "core-v1.3",
                "current_prompt_path": "prompts/page-01.md",
                "character_reference_path": "references/characters.png",
                "production_reference_path": "references/production.png",
            })
            (book / "page-manifest.json").write_text(json.dumps({"schema_version": 1, "age_band": "3-4", "pages": [page]}), encoding="utf-8")
            (book / "storyboard.json").write_text(json.dumps({"pages": [page]}), encoding="utf-8")
            (book / "layout.json").write_text(json.dumps({"pages": [{"page": 1, "style_version": "STYLE-06 v0.1"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CONTINUITY_SCHEMA_INVALID"):
                init_queue(book, book / "queue.json")

    def test_continuity_reference_hash_is_in_the_claimed_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp) / "book"
            book.mkdir()
            (book / "prompts").mkdir()
            (book / "references").mkdir()
            (book / "story.md").write_text("offline", encoding="utf-8")
            (book / "prompts" / "page-01.md").write_text("prompt", encoding="utf-8")
            (book / "references" / "characters.png").write_bytes(b"characters")
            (book / "references" / "production.png").write_bytes(b"production")
            reference = book / "references" / "page-01.png"
            reference.write_bytes(b"reference")
            page = _page(1, invariants=_valid_invariants("references/page-01.png", _sha256(reference)))
            page.update({
                "text_version": "v1",
                "characters_version": "core-v1.3",
                "current_prompt_path": "prompts/page-01.md",
                "character_reference_path": "references/characters.png",
                "production_reference_path": "references/production.png",
            })
            (book / "page-manifest.json").write_text(json.dumps({"schema_version": 1, "age_band": "3-4", "pages": [page]}), encoding="utf-8")
            (book / "storyboard.json").write_text(json.dumps({"pages": [page]}), encoding="utf-8")
            (book / "layout.json").write_text(json.dumps({"pages": [{"page": 1, "style_version": "STYLE-06 v0.1"}]}), encoding="utf-8")
            state = init_queue(book, book / "queue.json")
            claimed = importlib.import_module("generation_queue").claim_job(book / "queue.json", 1)
            self.assertEqual(claimed["continuity_task"]["status"], "ready")
            self.assertEqual(
                claimed["continuity_task"]["binding"]["reference_pages"][0]["sha256"],
                _sha256(reference),
            )

    def test_three_historical_cases_are_supported_offline(self):
        cases = {
            "seed": _valid_invariants(),
            "shadow": {
                "schema_version": 1,
                "scene_and_lighting": {
                    "scene_id": "warm-yard",
                    "light_direction": "upper-left",
                    "shadow_direction": "lower-right",
                    "shadow_foot_connection": True,
                    "shadow_rules": ["two distinct shadows", "each shadow connects to its character's feet"],
                },
                "character": [{"character_id": "CHAR-GIRL-01", "required_action": "compare shadows"}],
            },
            "leaves": {
                "schema_version": 1,
                "character": [
                    {
                        "character_id": "CHAR-GIRL-01",
                        "required_action": "sort leaves",
                        "before_state": "leaves mixed",
                        "current_state": "leaves grouped by color",
                        "after_state": "children change the sorting rule",
                    },
                    {
                        "character_id": "CHAR-BOY-01",
                        "required_action": "observe leaves",
                        "before_state": "leaves mixed",
                        "current_state": "leaf states are visible",
                        "after_state": "walk home with the group",
                    },
                ],
                "science_stages": {
                    "current_stage_id": "ground-leaf-observation",
                    "stage_order": 7,
                    "visible_parts": ["ground leaves"],
                    "next_stage_id": "story-end",
                },
            },
        }
        for name, invariants in cases.items():
            with self.subTest(case=name):
                result = validate_continuity_invariants(_page(1, invariants=invariants))
                self.assertEqual(result["blocks"], [])

    def test_continuity_fingerprint_is_deterministic_and_page_local(self):
        first = _page(1, invariants=_valid_invariants())
        second = _page(2)
        self.assertEqual(image_dependency_fingerprint(first), image_dependency_fingerprint(copy.deepcopy(first)))
        self.assertNotEqual(image_dependency_fingerprint(first), image_dependency_fingerprint(second))

    def test_queue_task_assembly_contains_constraints_and_localizes_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp) / "book"
            book.mkdir()
            (book / "prompts").mkdir()
            (book / "references").mkdir()
            (book / "story.md").write_text("一个离线测试故事。", encoding="utf-8")
            (book / "prompts" / "page-01.md").write_text("prompt 1", encoding="utf-8")
            (book / "prompts" / "page-02.md").write_text("prompt 2", encoding="utf-8")
            (book / "references" / "characters.png").write_bytes(b"characters")
            (book / "references" / "production.png").write_bytes(b"production")
            reference = book / "references" / "page-01.png"
            reference.write_bytes(b"page-reference")
            invariants = _valid_invariants("references/page-01.png", _sha256(reference))
            pages = [
                _page(1, invariants=invariants),
                _page(2),
            ]
            for page in pages:
                page.update(
                    {
                        "text_version": "story-v1",
                        "characters_version": "core-v1.3",
                        "current_prompt_path": f"prompts/page-{page['page']:02d}.md",
                        "character_reference_path": "references/characters.png",
                        "production_reference_path": "references/production.png",
                    }
                )
            manifest = {"schema_version": 1, "title": "offline", "age_band": "3-4", "pages": pages}
            storyboard_pages = [dict(page) for page in pages]
            (book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (book / "storyboard.json").write_text(json.dumps({"pages": storyboard_pages}), encoding="utf-8")
            (book / "layout.json").write_text(json.dumps({"pages": [{"page": 1, "style_version": "STYLE-06 v0.1"}, {"page": 2, "style_version": "STYLE-06 v0.1"}]}), encoding="utf-8")
            queue = book / "queue.json"
            state = init_queue(book, queue)
            job_by_page = {job["page"]: job for job in state["jobs"]}
            self.assertIn("continuity_task", job_by_page[1])
            self.assertIn("低矮、宽口、透明观察杯", job_by_page[1]["continuity_task"]["prompt_addendum"])
            self.assertEqual(
                job_by_page[1]["page_task"]["continuity_review_record"]["human_final_conclusion"],
                "pending",
            )
            self.assertEqual(job_by_page[2]["continuity_task"]["status"], "not_applicable")
            before_1 = job_by_page[1]["base_request_fingerprint"]
            before_2 = job_by_page[2]["base_request_fingerprint"]

            manifest["pages"][0]["continuity_invariants"]["scene_and_lighting"]["light_direction"] = "窗户右上方"
            (book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            updated = init_queue(book, queue)
            updated_by_page = {job["page"]: job for job in updated["jobs"]}
            self.assertNotEqual(updated_by_page[1]["base_request_fingerprint"], before_1)
            self.assertEqual(updated_by_page[2]["base_request_fingerprint"], before_2)


if __name__ == "__main__":
    unittest.main()

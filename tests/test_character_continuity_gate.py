from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


SKILL_DIR = Path(
    os.environ.get(
        "PICTUREBOOKS_SKILL_DIR",
        str(Path(__file__).parents[1]),
    )
).resolve()
SCRIPTS = SKILL_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import page_production  # noqa: E402


def load_queue_module():
    path = SCRIPTS / "generation_queue.py"
    spec = importlib.util.spec_from_file_location("generation_queue_continuity_gate", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _page(number: int = 1) -> dict:
    return {
        "page": number,
        "page_id": f"PAGE-{number:02d}",
        "page_version": "v1",
        "character_asset_bundle": "core-characters-v1.3",
        "character_asset_version": "v1.3",
        "characters": [
            {
                "character_id": "xiaoxiong",
                "identity_asset_id": "G-ID-01",
                "outfit_id": "G-01",
                "expression_id": "G-EX-01",
                "pose_id": "G-PO-01",
                "angle_id": "ANG-01",
            }
        ],
        "style_master_id": "STYLE-CORE-01",
        "style_master_version": "v1.2",
        "page_delta": {"story": f"第{number}页"},
        "current_prompt_path": f"prompts/page-{number:02d}.md",
        "character_reference_path": "characters/v1/production-reference.png",
        "production_reference_path": "characters/v1/production-reference.png",
    }


class CharacterContinuityGateTests(unittest.TestCase):
    def test_assembled_task_has_immutable_outfit_lock(self):
        task = page_production.assemble_page_task(_page())
        lock = task["prompt_contract"]["outfit_lock"]
        self.assertEqual(lock["status"], "locked")
        self.assertEqual(lock["characters"][0]["outfit_id"], "G-01")
        self.assertIn("Do not change clothing or footwear", lock["host_instruction"])

    def test_unapproved_outfit_override_is_rejected_before_host_submission(self):
        task = page_production.assemble_page_task(_page())
        with self.assertRaisesRegex(ValueError, "PROMPT_OUTFIT_CONFLICT"):
            page_production.validate_host_prompt(
                task,
                "保持同一位小女孩身份，穿黄色雨衣和红色雨靴，不要画动物熊。",
            )
        receipt = page_production.validate_host_prompt(task, "小熊沿着雨后地面的细窄湿痕走。")
        self.assertEqual(receipt["status"], "accepted")
        locked_prompt = page_production.build_host_prompt(task, "小熊沿着雨后地面的细窄湿痕走。")
        self.assertTrue(locked_prompt.startswith("OUTFIT_LOCK:G-01"))
        self.assertEqual(page_production.validate_host_prompt(task, locked_prompt)["status"], "accepted")

    def test_reference_receipt_separates_declared_paths_from_host_evidence(self):
        queue = load_queue_module()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prompts").mkdir(parents=True)
            (root / "characters" / "v1").mkdir(parents=True)
            (root / "characters" / "v1" / "production-reference.png").write_bytes(b"reference")
            (root / "story.md").write_text("第一页：小熊观察。\n", encoding="utf-8")
            page = {
                "page": 1,
                "text_version": "v1",
                "characters_version": "v1",
                "character_asset_bundle": "core-characters-v1.3",
                "character_asset_version": "v1.3",
                "characters": [
                    {
                        "character_id": "xiaoxiong",
                        "identity_asset_id": "G-ID-01",
                        "outfit_id": "G-01",
                        "expression_id": "G-EX-01",
                        "pose_id": "G-PO-01",
                        "angle_id": "ANG-01",
                    }
                ],
                "style_master_id": "STYLE-CORE-01",
                "style_master_version": "v1.2",
                "page_delta": {"story": "小熊观察"},
                "character_reference_path": "characters/v1/production-reference.png",
                "production_reference_path": "characters/v1/production-reference.png",
                "current_prompt_path": "prompts/page-01.md",
                "current_image_path": None,
                "story_dependency": {"lines": [1, 1]},
            }
            (root / "prompts" / "page-01.md").write_text("小熊观察。", encoding="utf-8")
            for name, pages in (
                ("page-manifest.json", {"title": "测试", "age_band": "5-7", "pages": [page]}),
                ("storyboard.json", {"pages": [page]}),
                ("layout.json", {"pages": [page]}),
            ):
                (root / name).write_text(json.dumps(pages), encoding="utf-8")
            queue_path = root / "queue.json"
            queue.init_queue(root, queue_path, max_in_flight=1, require_visual_review=True)
            claimed = queue.claim_job(queue_path, 1)
            with self.assertRaisesRegex(ValueError, "PROMPT_OUTFIT_CONFLICT"):
                queue.mark_request_submitted(
                    queue_path,
                    claimed["current_request_id"],
                    prompt_text="保持身份但穿黄色雨衣和红色雨靴。",
                )
            request = queue.mark_request_submitted(queue_path, claimed["current_request_id"])
            self.assertEqual(request["reference_submission"]["status"], "declared_not_observed")
            self.assertEqual(
                request["reference_submission"]["declared_paths"],
                [
                    "characters/v1/production-reference.png",
                    "characters/v1/production-reference.png",
                ],
            )
            self.assertIsNone(request["reference_submission"]["host_evidence"])
            request = queue.mark_request_submitted(
                queue_path,
                claimed["current_request_id"],
                prompt_text="小熊沿着雨后地面的细窄湿痕走。",
            )
            self.assertEqual(request["prompt_submission"]["status"], "observed_and_validated")

    def test_visual_review_gate_blocks_failed_or_pending_page_and_allows_passed_page(self):
        queue = load_queue_module()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_book(queue, root, pages=2)
            queue_path = root / "queue.json"
            queue.init_queue(root, queue_path, max_in_flight=1, require_visual_review=True)
            first = queue.claim_job(queue_path, 1)
            queue.mark_request_submitted(queue_path, first["current_request_id"])
            output = root / "images" / "page-01.png"
            output.parent.mkdir()
            Image.new("RGB", (1024, 1024), (120, 180, 220)).save(output)
            queue.complete_job(queue_path, 1, output)
            with self.assertRaisesRegex(RuntimeError, "VISUAL_REVIEW_REQUIRED"):
                queue.claim_job(queue_path, 2)
            failed = queue.record_visual_review(
                queue_path,
                1,
                "failed",
                evidence="第5页出现黄色雨衣和红色雨靴，违反G-01服装锁定。",
                reviewer_type="offline-fixture",
            )
            self.assertEqual(failed["visual_review"]["status"], "failed")
            with self.assertRaisesRegex(RuntimeError, "VISUAL_REVIEW_REQUIRED"):
                queue.claim_job(queue_path, 2)
            passed = queue.record_visual_review(
                queue_path,
                1,
                "passed",
                evidence="离线回归夹具：服装与G-01一致。",
                reviewer_type="offline-fixture",
            )
            self.assertEqual(passed["visual_review"]["status"], "passed")
            second = queue.claim_job(queue_path, 2)
            self.assertEqual(second["page"], 2)

    @staticmethod
    def _write_book(queue, root: Path, *, pages: int) -> None:
        (root / "prompts").mkdir(parents=True)
        (root / "characters" / "v1").mkdir(parents=True)
        (root / "characters" / "v1" / "production-reference.png").write_bytes(b"reference")
        (root / "story.md").write_text("\n".join(f"第{i}页：小熊观察。" for i in range(1, pages + 1)), encoding="utf-8")
        records = []
        for i in range(1, pages + 1):
            (root / "prompts" / f"page-{i:02d}.md").write_text(f"第{i}页提示词", encoding="utf-8")
            records.append(
                {
                    "page": i,
                    "text_version": "v1",
                    "characters_version": "v1",
                    "character_reference_path": "characters/v1/production-reference.png",
                    "production_reference_path": "characters/v1/production-reference.png",
                    "current_prompt_path": f"prompts/page-{i:02d}.md",
                    "current_image_path": None,
                    "story_dependency": {"lines": [i, i]},
                }
            )
        for name, document in (
            ("page-manifest.json", {"title": "测试", "age_band": "5-7", "pages": records}),
            ("storyboard.json", {"pages": records}),
            ("layout.json", {"pages": records}),
        ):
            (root / name).write_text(json.dumps(document), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

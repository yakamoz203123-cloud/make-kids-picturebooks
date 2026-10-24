import importlib.util
import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "generation_queue.py"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError(f"missing production queue script: {SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("generation_queue_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenerationQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.book = self.root / "book"
        self.queue = self.root / "queue.json"
        self._make_book()
        self.module = load_module()

    def tearDown(self):
        self.temp.cleanup()

    def _make_book(self, pages=3):
        (self.book / "prompts").mkdir(parents=True)
        (self.book / "characters" / "v1").mkdir(parents=True)
        (self.book / "characters" / "v1" / "production-reference.png").write_bytes(b"ref")
        (self.book / "story.md").write_text(
            "第一页：小朋友观察花环如何诞生。\n"
            "第二页：小朋友发现花环需要一步一步完成。\n"
            "第三页：小朋友把花环挂在门上。\n",
            encoding="utf-8",
        )
        page_list = []
        for page in range(1, pages + 1):
            prompt_path = self.book / "prompts" / f"page-{page:02d}.md"
            prompt_path.write_text(f"第{page}页插画提示词", encoding="utf-8")
            page_list.append(
                {
                    "page": page,
                    "text_version": "v1",
                    "characters_version": "v1",
                    "character_reference_path": "characters/v1/production-reference.png",
                    "production_reference_path": "characters/v1/production-reference.png",
                    "current_prompt_path": f"prompts/page-{page:02d}.md",
                    "current_image_path": None,
                    "story_dependency": {"lines": [page, page]},
                }
            )
        common = {"title": "测试绘本", "age_band": "5-7", "pages": page_list}
        (self.book / "page-manifest.json").write_text(json.dumps(common), encoding="utf-8")
        (self.book / "storyboard.json").write_text(json.dumps({"pages": page_list}), encoding="utf-8")
        layout_pages = []
        for page in page_list:
            layout_page = dict(page)
            layout_page["source_aspect_ratio"] = "1:1"
            layout_pages.append(layout_page)
        (self.book / "layout.json").write_text(json.dumps({"pages": layout_pages}), encoding="utf-8")

    def _write_image(self, path, *, size=(1024, 1024), color=(120, 180, 220)):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size, color)
        image.save(path, format="PNG")

    def _write_success_image(self, page, *, size=(1024, 1024), color=None):
        output = self.book / "images" / f"page-{page:02d}.png"
        self._write_image(output, size=size, color=color or (page * 20, 100, 160))
        return output

    def _claim_and_mark_submitted(self, page):
        claimed = self.module.claim_job(self.queue, page)
        self.module.mark_request_submitted(self.queue, claimed["current_request_id"])
        return claimed

    def _init(self, **kwargs):
        return self.module.init_queue(self.book, self.queue, **kwargs)

    def _write_manifest(self, manifest):
        (self.book / "page-manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

    def _make_formal_canvas_book(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        storyboard = json.loads((self.book / "storyboard.json").read_text(encoding="utf-8"))
        layout = json.loads((self.book / "layout.json").read_text(encoding="utf-8"))
        for document in (manifest, storyboard):
            for page in document["pages"]:
                page["profile"] = "xiaohongshu-feed-3x4"
                page["declared_aspect_ratio"] = "3:4"
        for page in layout["pages"]:
            page["profile"] = "xiaohongshu-feed-3x4"
            page["source_aspect_ratio"] = "3:4"
            page["social_layout"] = {
                "profile": "xiaohongshu-feed-3x4",
                "canvas": {"width_px": 1080, "height_px": 1440},
                "source_aspect_ratio": "3:4",
            }
        (self.book / "page-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (self.book / "storyboard.json").write_text(
            json.dumps(storyboard), encoding="utf-8"
        )
        (self.book / "layout.json").write_text(json.dumps(layout), encoding="utf-8")

    def test_init_rejects_incomplete_plan_before_creating_queue(self):
        storyboard = json.loads((self.book / "storyboard.json").read_text(encoding="utf-8"))
        storyboard["pages"] = storyboard["pages"][:-1]
        (self.book / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")
        with self.assertRaises(ValueError):
            self._init()
        self.assertFalse(self.queue.exists())

    def test_init_creates_one_job_per_page_with_bounded_default(self):
        state = self._init()
        self.assertEqual(state["max_in_flight"], 2)
        self.assertEqual(len(state["jobs"]), 3)
        self.assertTrue(all(job["status"] == "pending" for job in state["jobs"]))
        self.assertEqual(len({job["output_path"] for job in state["jobs"]}), 3)
        self.assertTrue(all(job["request_fingerprint"] for job in state["jobs"]))

    def test_production_queue_requires_explicit_generation_authorization(self):
        self._init()
        state = json.loads(self.queue.read_text(encoding="utf-8"))
        state["requires_user_authorization"] = True
        state["workflow_gate"] = {"mode": "production"}
        self.queue.write_text(json.dumps(state), encoding="utf-8")

        with self.assertRaisesRegex(PermissionError, "generation authorization"):
            self.module.claim_job(self.queue, 1)

        authorization = self.module.authorize_generation(
            self.queue,
            approval="user-approved-batch",
            max_calls=1,
        )
        claimed = self.module.claim_job(
            self.queue,
            1,
            authorization_id=authorization["authorization_id"],
        )
        self.assertEqual(claimed["generation_authorization_id"], authorization["authorization_id"])

        with self.assertRaisesRegex(PermissionError, "already been used|no unused"):
            self.module.claim_job(
                self.queue,
                2,
                authorization_id=authorization["authorization_id"],
            )

    def test_init_accepts_content_layout_and_keeps_book_relative_inputs(self):
        content = self.book / "content"
        content.mkdir()
        for name in ("story.md", "page-manifest.json", "storyboard.json", "layout.json", "prompts", "characters"):
            shutil.move(str(self.book / name), str(content / name))

        state = self._init()

        self.assertEqual(state["page_count"], 3)
        self.assertTrue(all(job["status"] == "pending" for job in state["jobs"]))
        self.assertTrue(all(job["output_path"].startswith("images/") for job in state["jobs"]))

    def test_init_rejects_absolute_and_parent_input_paths(self):
        outside_prompt = self.root / "outside-prompt.md"
        outside_prompt.write_text("项目目录之外的提示词", encoding="utf-8")
        outside_reference = self.root / "outside-reference.png"
        outside_reference.write_bytes(b"outside-reference")
        cases = {
            "current_prompt_path": outside_prompt,
            "character_reference_path": outside_reference,
            "production_reference_path": outside_reference,
        }
        baseline = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))

        for field, outside_path in cases.items():
            for kind, value in (
                ("absolute", str(outside_path)),
                ("parent traversal", f"../{outside_path.name}"),
            ):
                with self.subTest(field=field, kind=kind):
                    manifest = json.loads(json.dumps(baseline))
                    page_indexes = [0] if field == "current_prompt_path" else range(len(manifest["pages"]))
                    for page_index in page_indexes:
                        manifest["pages"][page_index][field] = value
                    self._write_manifest(manifest)
                    self.queue.unlink(missing_ok=True)

                    with self.assertRaisesRegex(ValueError, "inside book directory|relative|contain"):
                        self._init()
                    self.assertFalse(self.queue.exists())

    def test_init_rejects_symlink_escape_for_all_input_paths(self):
        outside_prompt = self.root / "outside-prompt.md"
        outside_prompt.write_text("项目目录之外的提示词", encoding="utf-8")
        outside_reference = self.root / "outside-reference.png"
        outside_reference.write_bytes(b"outside-reference")
        escaped_dir = self.book / "escaped"
        escaped_dir.mkdir()
        try:
            os.symlink(outside_prompt, escaped_dir / "prompt.md")
            os.symlink(outside_reference, escaped_dir / "reference.png")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        cases = {
            "current_prompt_path": "escaped/prompt.md",
            "character_reference_path": "escaped/reference.png",
            "production_reference_path": "escaped/reference.png",
        }
        baseline = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        for field, value in cases.items():
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(baseline))
                page_indexes = [0] if field == "current_prompt_path" else range(len(manifest["pages"]))
                for page_index in page_indexes:
                    manifest["pages"][page_index][field] = value
                self._write_manifest(manifest)
                self.queue.unlink(missing_ok=True)

                with self.assertRaisesRegex(ValueError, "inside book directory"):
                    self._init()
                self.assertFalse(self.queue.exists())

    def test_claim_enforces_max_in_flight_and_complete_releases_slot(self):
        self._init(max_in_flight=2)
        self._claim_and_mark_submitted(1)
        self._claim_and_mark_submitted(2)
        with self.assertRaises(RuntimeError):
            self.module.claim_job(self.queue, 3)
        output = self._write_success_image(1)
        completed = self.module.complete_job(self.queue, 1, output)
        self.assertEqual(
            completed["image_validation"],
            {
                "width_px": 1024,
                "height_px": 1024,
                "format": "PNG",
                "aspect_ratio": "1:1",
            },
        )
        claimed = self.module.claim_job(self.queue, 3)
        self.assertEqual(claimed["page"], 3)

    def test_formal_profile_rejects_wrong_exact_canvas_on_completion(self):
        self._make_formal_canvas_book()
        self._init()
        self._claim_and_mark_submitted(1)
        output = self._write_success_image(1, size=(1086, 1448))

        with self.assertRaisesRegex(ValueError, "exact canvas.*1086x1448.*1080x1440"):
            self.module.complete_job(self.queue, 1, output)

    def test_formal_profile_does_not_cache_wrong_exact_canvas(self):
        self._make_formal_canvas_book()
        output = self._write_success_image(1, size=(1086, 1448))

        state = self._init()
        page_one = next(job for job in state["jobs"] if job["page"] == 1)

        self.assertEqual("pending", page_one["status"])
        self.assertIn("exact canvas", page_one["last_error"])

    def test_formal_profile_accepts_exact_canvas(self):
        self._make_formal_canvas_book()
        self._init()
        self._claim_and_mark_submitted(1)
        output = self._write_success_image(1, size=(1080, 1440))

        completed = self.module.complete_job(self.queue, 1, output)

        self.assertEqual("completed", completed["status"])
        self.assertEqual([1080, 1440], [completed["image_validation"]["width_px"], completed["image_validation"]["height_px"]])

    def test_claim_batch_is_atomic_and_bounded(self):
        self._init(max_in_flight=2)
        claimed = self.module.claim_batch(self.queue, [1, 2])
        self.assertEqual([job["page"] for job in claimed], [1, 2])
        with self.assertRaises(RuntimeError):
            self.module.claim_batch(self.queue, [3])
        state = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual([job["status"] for job in state["jobs"]], ["running", "running", "pending"])

    def test_reinitialization_does_not_trust_changed_completed_output(self):
        self._init()
        self._claim_and_mark_submitted(1)
        output = self._write_success_image(1)
        self.module.complete_job(self.queue, 1, output)
        self._write_image(output, color=(220, 80, 80))
        state = self._init()
        job = next(job for job in state["jobs"] if job["page"] == 1)
        self.assertEqual(job["status"], "pending")
        self.assertIsNone(job["output_sha256"])

    def test_failures_retry_then_become_terminal(self):
        self._init(max_attempts=2)
        self._claim_and_mark_submitted(1)
        first = self.module.fail_job(self.queue, 1, "temporary tool failure")
        self.assertEqual(first["status"], "retryable")
        self._claim_and_mark_submitted(1)
        second = self.module.fail_job(self.queue, 1, "same failure")
        self.assertEqual(second["status"], "failed")
        self.assertEqual(second["attempts"], 2)
        self.assertEqual(len(second["errors"]), 2)

    def test_resume_preserves_completed_pages_and_requeues_running_pages(self):
        self._init()
        self._claim_and_mark_submitted(1)
        self.module.claim_job(self.queue, 2)
        output = self._write_success_image(1)
        self.module.complete_job(self.queue, 1, output)
        state = self.module.resume_queue(self.queue)
        jobs = {job["page"]: job for job in state["jobs"]}
        self.assertEqual(jobs[1]["status"], "completed")
        self.assertEqual(jobs[2]["status"], "retryable")

    def test_reset_page_only_invalidates_selected_page_and_keeps_old_output(self):
        self._init()
        for page in (1, 2):
            self._claim_and_mark_submitted(page)
            output = self._write_success_image(page)
            self.module.complete_job(self.queue, page, output)
        state = self.module.reset_page(self.queue, 2, "用户修改第2页动作")
        jobs = {job["page"]: job for job in state["jobs"]}
        self.assertEqual(jobs[1]["status"], "completed")
        self.assertEqual(jobs[2]["status"], "pending")
        self.assertEqual(jobs[2]["revision"], 2)
        self.assertTrue(jobs[2]["previous_output_path"].endswith("page-02.png"))
        self.assertTrue((self.book / jobs[2]["previous_output_path"]).exists())
        self.assertNotEqual(jobs[2]["request_fingerprint"], jobs[1]["request_fingerprint"])
        self.assertIsNone(jobs[2]["output_sha256"])
        self.assertIsNone(jobs[2]["elapsed_ms"])
        self.assertNotIn("image_validation", jobs[2])
        self.assertNotIn("started_at", jobs[2])
        self.assertNotIn("finished_at", jobs[2])

    def test_reinitialization_detects_existing_output_as_cache(self):
        (self.book / "images").mkdir()
        for page in range(1, 4):
            output = self.book / "images" / f"page-{page:02d}.png"
            self._write_image(output, color=(page * 20, 140, 80))
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            page["current_image_path"] = f"images/page-{page['page']:02d}.png"
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        state = self._init()
        self.assertTrue(all(job["status"] == "cached" for job in state["jobs"]))
        self.assertEqual(self.module.status(self.queue)["counts"]["cached"], 3)

    def test_page_scoped_story_dependency_only_invalidates_affected_page(self):
        self._init()
        for page in (1, 2):
            self._claim_and_mark_submitted(page)
            self.module.complete_job(self.queue, page, self._write_success_image(page))

        story = (self.book / "story.md").read_text(encoding="utf-8")
        self.assertIn("第二页", story)
        (self.book / "story.md").write_text(
            story.replace("小朋友发现花环需要一步一步完成", "小朋友发现花环需要耐心完成"),
            encoding="utf-8",
        )

        state = self._init()
        jobs = {job["page"]: job for job in state["jobs"]}
        self.assertEqual(jobs[1]["status"], "cached")
        self.assertEqual(jobs[2]["status"], "pending")
        self.assertEqual(jobs[1]["story_dependency_mode"], "page")
        self.assertEqual(jobs[1]["story_dependency_scope"], "page")

    def test_asset_and_style_dependencies_invalidate_only_the_changed_page(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            page.update({
                "page_id": f"PAGE-{page['page']:02d}",
                "page_version": f"PAGE-{page['page']:02d}-v1",
                "resolved_asset_hash": f"asset-hash-{page['page']}",
                "style_master_content_hash": "style-hash-v1",
            })
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        self._init()
        for page in (1, 2):
            self._claim_and_mark_submitted(page)
            self.module.complete_job(self.queue, page, self._write_success_image(page))

        manifest["pages"][1]["resolved_asset_hash"] = "asset-hash-2-v2"
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        state = self._init()
        jobs = {job["page"]: job for job in state["jobs"]}

        self.assertEqual(jobs[1]["status"], "cached")
        self.assertEqual(jobs[2]["status"], "pending")
        self.assertEqual(jobs[3]["status"], "pending")
        self.assertNotEqual(
            jobs[2]["asset_dependency_fingerprint"],
            jobs[1]["asset_dependency_fingerprint"],
        )
        self.assertEqual(jobs[1]["page_version"], "PAGE-01-v1")

    def test_storyboard_image_dependencies_change_asset_fingerprint(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        storyboard = json.loads((self.book / "storyboard.json").read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            page.update({
                "page_id": f"PAGE-{page['page']:02d}",
                "page_version": f"PAGE-{page['page']:02d}-v1",
                "resolved_asset_hash": f"manifest-asset-hash-{page['page']}",
                "style_master_content_hash": "style-hash-v1",
            })
        for page in storyboard["pages"]:
            page.update({
                "page_id": f"PAGE-{page['page']:02d}",
                "page_version": f"PAGE-{page['page']:02d}-v1",
                "resolved_asset_hash": f"storyboard-asset-hash-{page['page']}",
                "style_master_content_hash": "style-hash-v1",
            })
        self._write_manifest(manifest)
        (self.book / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")

        self._init()
        self._claim_and_mark_submitted(1)
        self.module.complete_job(self.queue, 1, self._write_success_image(1))
        before = next(job for job in json.loads(self.queue.read_text(encoding="utf-8"))["jobs"] if job["page"] == 1)

        storyboard["pages"][0]["resolved_asset_hash"] = "storyboard-asset-hash-1-v2"
        storyboard["pages"][0]["page_delta"] = {"scene": "资产变化后的场景"}
        (self.book / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")

        state = self._init()
        job = next(job for job in state["jobs"] if job["page"] == 1)
        self.assertEqual(job["status"], "pending")
        self.assertNotEqual(
            job["asset_dependency_fingerprint"],
            before["asset_dependency_fingerprint"],
        )

    def test_manifest_title_only_change_does_not_redraw_completed_images(self):
        self._init()
        for page in (1, 2):
            self._claim_and_mark_submitted(page)
            self.module.complete_job(self.queue, page, self._write_success_image(page))

        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        manifest["title"] = "只改书名，不改画面依赖"
        self._write_manifest(manifest)

        state = self._init()
        jobs = {job["page"]: job for job in state["jobs"]}
        self.assertEqual(jobs[1]["status"], "cached")
        self.assertEqual(jobs[2]["status"], "cached")
        self.assertEqual(jobs[3]["status"], "pending")

    def test_text_only_page_edit_does_not_redraw_completed_image(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            page.update({
                "page_id": f"PAGE-{page['page']:02d}",
                "page_version": f"PAGE-{page['page']:02d}-v1",
                "text": f"原始第{page['page']}页文字。",
                "resolved_asset_hash": f"asset-hash-{page['page']}",
                "style_master_content_hash": "style-hash-v1",
            })
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        self._init()
        for page in (1, 2):
            self._claim_and_mark_submitted(page)
            self.module.complete_job(self.queue, page, self._write_success_image(page))

        manifest["pages"][0]["text"] = "只修改文字，不修改画面。"
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        state = self._init()
        jobs = {job["page"]: job for job in state["jobs"]}

        self.assertEqual(jobs[1]["status"], "cached")
        self.assertEqual(jobs[2]["status"], "cached")

    def test_queue_events_carry_page_version_revision_and_failure_code(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        manifest["pages"][0].update({
            "page_id": "PAGE-01",
            "page_version": "PAGE-01-v3",
            "resolved_asset_hash": "asset-hash-1",
            "style_master_content_hash": "style-hash-v1",
        })
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        self._init()
        self._claim_and_mark_submitted(1)
        self.module.fail_job(self.queue, 1, "image decode failed", failure_code="INVALID_IMAGE")
        state = json.loads(self.queue.read_text(encoding="utf-8"))
        failed = [event for event in state["events"] if event["event"] == "failed"][-1]

        self.assertEqual(failed["page_id"], "PAGE-01")
        self.assertEqual(failed["page_version"], "PAGE-01-v3")
        self.assertEqual(failed["revision"], 1)
        self.assertEqual(failed["failure_code"], "INVALID_IMAGE")
        self.assertEqual(state["jobs"][0]["last_failure_code"], "INVALID_IMAGE")

    def test_story_change_without_page_dependency_conservatively_invalidates_completed_page(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        storyboard = json.loads((self.book / "storyboard.json").read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            page.pop("story_dependency", None)
        for page in storyboard["pages"]:
            page.pop("story_dependency", None)
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.book / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")

        self._init()
        self._claim_and_mark_submitted(1)
        self.module.complete_job(self.queue, 1, self._write_success_image(1))
        (self.book / "story.md").write_text(
            (self.book / "story.md").read_text(encoding="utf-8") + "\n故事结尾发生了变化。\n",
            encoding="utf-8",
        )

        state = self._init()
        job = next(job for job in state["jobs"] if job["page"] == 1)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["story_dependency_mode"], "book")
        self.assertEqual(job["story_dependency_scope"], "whole-story")

    def test_invalid_page_dependencies_fall_back_to_whole_story(self):
        story_path = self.book / "story.md"
        story_text = story_path.read_text(encoding="utf-8")
        whole_story_sha256 = self.module._file_hash(story_path)
        duplicate_text = "第一页：小朋友观察花环如何诞生。"
        (self.book / "story-with-duplicate.md").write_text(
            story_text + duplicate_text + "\n",
            encoding="utf-8",
        )
        cases = [
            ("missing path", {"path": "missing.md", "lines": [1, 1]}, story_text, story_path),
            ("out of range", {"lines": [1, 999]}, story_text, story_path),
            ("invalid line", {"lines": [0, 1]}, story_text, story_path),
            ("ambiguous selectors", {"lines": [1, 1], "line_start": 1, "line_end": 1}, story_text, story_path),
            ("missing text", "这段文字不存在于故事中", story_text, story_path),
            ("duplicate text", duplicate_text, (self.book / "story-with-duplicate.md").read_text(encoding="utf-8"), self.book / "story-with-duplicate.md"),
        ]
        for label, dependency, source_text, source_path in cases:
            with self.subTest(label=label):
                source_hash = self.module._file_hash(source_path)
                scope, fingerprint = self.module._story_dependency_fingerprint(
                    source_text,
                    source_path,
                    self.book,
                    [dependency],
                    source_hash,
                )
                self.assertEqual(scope, "whole-story")
                self.assertEqual(fingerprint, source_hash)

    def test_invalid_page_dependency_invalidates_old_image_after_story_change(self):
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        storyboard = json.loads((self.book / "storyboard.json").read_text(encoding="utf-8"))
        invalid_dependency = {"lines": [1, 999]}
        manifest["pages"][0]["story_dependency"] = invalid_dependency
        storyboard["pages"][0]["story_dependency"] = invalid_dependency
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.book / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")

        self._init()
        self._claim_and_mark_submitted(1)
        self.module.complete_job(self.queue, 1, self._write_success_image(1))
        (self.book / "story.md").write_text(
            (self.book / "story.md").read_text(encoding="utf-8") + "\n故事结尾发生了变化。\n",
            encoding="utf-8",
        )

        state = self._init()
        job = next(job for job in state["jobs"] if job["page"] == 1)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["story_dependency_mode"], "book")
        self.assertEqual(job["story_dependency_scope"], "whole-story")

    def test_complete_rejects_text_corrupt_small_and_wrong_ratio_outputs(self):
        self._init(max_attempts=5)
        invalid_outputs = [
            ("text", b"not an image"),
            ("corrupt", b"\x89PNG\r\n\x1a\nnot-png"),
        ]
        for label, data in invalid_outputs:
            self._claim_and_mark_submitted(1)
            output = self.book / "images" / f"{label}.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "valid image"):
                self.module.complete_job(self.queue, 1, output)
            self.module.fail_job(self.queue, 1, label)

        self._claim_and_mark_submitted(1)
        small = self.book / "images" / "small.png"
        self._write_image(small, size=(512, 512))
        with self.assertRaisesRegex(ValueError, "1024"):
            self.module.complete_job(self.queue, 1, small)
        self.module.fail_job(self.queue, 1, "small")

        self._claim_and_mark_submitted(1)
        wrong_ratio = self.book / "images" / "wrong-ratio.png"
        self._write_image(wrong_ratio, size=(1024, 1200))
        with self.assertRaisesRegex(ValueError, "aspect ratio"):
            self.module.complete_job(self.queue, 1, wrong_ratio)

    def test_invalid_existing_output_is_not_marked_as_cache(self):
        output = self.book / "images" / "page-01.png"
        output.parent.mkdir()
        output.write_bytes(b"not an image")
        manifest = json.loads((self.book / "page-manifest.json").read_text(encoding="utf-8"))
        manifest["pages"][0]["current_image_path"] = "images/page-01.png"
        (self.book / "page-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        state = self._init()
        job = next(job for job in state["jobs"] if job["page"] == 1)
        self.assertEqual(job["status"], "pending")
        self.assertIsNone(job["output_sha256"])

    def test_queue_declares_single_coordinator_and_releases_lock(self):
        state = self._init()
        self.assertEqual(state["coordination_mode"], "single-coordinator")
        self.module.claim_job(self.queue, 1)
        self.assertFalse(Path(f"{self.queue}.lock").exists())

    def test_queue_lock_rejects_another_mutation(self):
        self._init()
        lock_path = Path(f"{self.queue}.lock")
        lock_path.write_text("held by another coordinator", encoding="utf-8")
        original_timeout = self.module.QUEUE_LOCK_TIMEOUT_SECONDS
        self.module.QUEUE_LOCK_TIMEOUT_SECONDS = 0.05
        try:
            with self.assertRaisesRegex(RuntimeError, "locked"):
                self.module.claim_job(self.queue, 1)
        finally:
            self.module.QUEUE_LOCK_TIMEOUT_SECONDS = original_timeout
            lock_path.unlink(missing_ok=True)

    def test_lock_contains_owner_token_and_release_does_not_delete_replacement(self):
        self._init()
        lock_path = Path(f"{self.queue}.lock")
        with self.module._queue_mutation_lock(self.queue):
            original = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertTrue(original["owner_token"])
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "created_at": "replacement",
                        "mode": self.module.COORDINATION_MODE,
                        "owner_token": "replacement-token",
                    }
                ),
                encoding="utf-8",
            )
        self.assertTrue(lock_path.exists())
        lock_path.unlink()

    def test_stale_lock_with_live_owner_is_not_reclaimed(self):
        self._init()
        lock_path = Path(f"{self.queue}.lock")
        lock_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "created_at": "old",
                    "mode": self.module.COORDINATION_MODE,
                    "owner_token": "live-owner",
                }
            ),
            encoding="utf-8",
        )
        old_time = time.time() - self.module.QUEUE_LOCK_STALE_SECONDS - 1
        os.utime(lock_path, (old_time, old_time))
        original_timeout = self.module.QUEUE_LOCK_TIMEOUT_SECONDS
        self.module.QUEUE_LOCK_TIMEOUT_SECONDS = 0.05
        try:
            with patch.object(self.module, "_pid_is_alive", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "locked"):
                    self.module.claim_job(self.queue, 1)
            self.assertTrue(lock_path.exists())
        finally:
            self.module.QUEUE_LOCK_TIMEOUT_SECONDS = original_timeout
            lock_path.unlink(missing_ok=True)

    def test_stale_lock_with_dead_owner_is_reclaimed(self):
        self._init()
        lock_path = Path(f"{self.queue}.lock")
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 999999999,
                    "created_at": "old",
                    "mode": self.module.COORDINATION_MODE,
                    "owner_token": "dead-owner",
                }
            ),
            encoding="utf-8",
        )
        old_time = time.time() - self.module.QUEUE_LOCK_STALE_SECONDS - 1
        os.utime(lock_path, (old_time, old_time))
        with patch.object(self.module, "_pid_is_alive", return_value=False):
            claimed = self.module.claim_job(self.queue, 1)
        self.assertEqual(claimed["status"], "running")
        self.assertFalse(lock_path.exists())

    def test_formal_production_queue_rejects_probe_sized_image(self):
        self._init()
        self._claim_and_mark_submitted(1)
        probe_sized = self.book / "images" / "probe-sized.png"
        self._write_image(probe_sized, size=(768, 1024))
        with self.assertRaisesRegex(ValueError, "1024"):
            self.module.complete_job(self.queue, 1, probe_sized)


if __name__ == "__main__":
    unittest.main()

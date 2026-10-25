from pathlib import Path
import json
import importlib
import subprocess
import sys
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (SKILL_DIR / relative_path).read_text(encoding="utf-8")


class SkillGuidanceTests(unittest.TestCase):
    def test_v2_role_lock_and_story_event_alignment_are_explicit_rules(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/characters.md",
                "references/production-workflow.md",
            )
        )
        for term in (
            "角色身份锁定",
            "系列角色优先",
            "规范角色名",
            "别名/同音字",
            "新角色必须",
            "正文中的多个重要动作或知识事件",
            "删减、拆分或重新安排",
            "儿童行动—期待—发现",
            "观察说明清单",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_v2_story_editing_and_full_book_direction_are_decision_rules(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/production-workflow.md",
                "references/review.md",
                "references/composition.md",
            )
        )
        for term in (
            "视觉事件驱动分页",
            "自主决定页数",
            "删除、合并、拆分或调整页面",
            "每页一个主要视觉任务",
            "整本视觉节奏",
            "相邻页重复审计",
            "有价值的重复",
            "先故事、再页面、再镜头",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_workflow_routes_to_continuity_and_final_gates(self) -> None:
        skill = read("SKILL.md")

        for link in (
            "references/characters.md",
            "references/composition.md",
            "references/page-records.md",
            "references/review.md",
            "references/printing.md",
            "references/acceptance.md",
        ):
            self.assertIn(link, skill)

        for term in (
            "manifest continuity fields",
            "state_id",
            "summary",
            "character_reference_path",
            "character bible",
            "adjacent-page pair",
            "text-image state matching",
            "validate_exports.py",
            "export_book.py",
            "acceptance",
            "references/research-input-gate.md",
            "knowledge-whitelist.json",
            "content_gate.py validate-packet",
            "content_gate.py validate-story",
        ):
            self.assertIn(term, skill)


    def test_reference_guidance_defines_structured_continuity_and_review(self) -> None:
        characters = read("references/characters.md")
        composition = read("references/composition.md")
        records = read("references/page-records.md")
        review = read("references/review.md")
        printing = read("references/printing.md")
        acceptance = read("references/acceptance.md")

        self.assertIn("character bible", characters)
        self.assertIn("character_reference_path", characters)
        self.assertIn("text-image state matching", composition)
        for term in ("state_id", "summary", '"status"', '"evidence"'):
            self.assertIn(term, records)
        self.assertIn("adjacent-page pair", review)
        self.assertIn("human/model visual review", review)
        for term in ("可嵌入的TrueType", "可提取文字", "最低打印字号"):
            with self.subTest(term=term):
                self.assertIn(term, printing)
        for term in ("font-license.txt", "font-provenance.json"):
            with self.subTest(term=term):
                self.assertIn(term, acceptance)
        self.assertIn("validate_exports.py", acceptance)
        self.assertIn("export_book.py", acceptance)
        self.assertIn("acceptance", acceptance)


    def test_private_real_child_character_guidance_is_explicit(self) -> None:
        skill = read("SKILL.md")
        characters = read("references/characters.md")

        for term in ("真实儿童", "私有项目", "privacy_scope", "public_release"):
            with self.subTest(term=term):
                self.assertIn(term, skill + characters)
        self.assertIn("不进入 Skill 仓库或 GitHub", skill + characters)
        for term in ("pending", "不等于", "approved"):
            self.assertIn(term, skill + characters)


    def test_fast_image_generation_protocol_is_explicit(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/characters.md",
                "references/social-output.md",
            )
        )

        for term in (
            "快速出图协议",
            "production_reference_path",
            "先完成 `layout_design` 再调用图像生成器",
            "每页一次生成",
            "两页一批",
            "不要重复提交",
            "先检查已有结果",
            "稳定基础提示词",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_production_queue_and_performance_protocol_are_explicit(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/production-workflow.md",
                "references/characters.md",
                "references/acceptance.md",
                "RELEASE.md",
            )
        )
        for term in (
            "generation_queue.py",
            "一次规划",
            "分阶段",
            "story.md",
            "storyboard.json",
            "max_in_flight",
            "默认串行",
            "2—3",
            "不是图片模型并发许可",
            "断点续跑",
            "缓存",
            "reset-page",
            "只重新生成该页",
            "一版完整成品",
            "不自动生成多套备选",
            "不接入新的付费图像接口",
            "总耗时",
            "失败率",
            "输出质量",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_v011_education_goal_card_is_complete_before_storyboarding(self) -> None:
        template_path = SKILL_DIR / "assets/education-goal-template.json"
        self.assertTrue(template_path.is_file(), "V0.11 education goal template is required")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        required_fields = {
            "core_knowledge",
            "target_age_band",
            "prior_experience",
            "visible_relationship",
            "knowledge_boundary",
            "reading_observation",
        }
        self.assertTrue(required_fields <= set(template))

        skill = read("SKILL.md")
        guidance = read("references/education-goals.md")
        combined = "\n".join((skill, guidance))
        for term in (
            "教育目标卡",
            "education-goal-template.json",
            "正式分镜前",
            "core_knowledge",
            "visible_relationship",
            "reading_observation",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_v011_evidence_domains_and_contact_sheet_review_are_separate(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/review.md",
                "references/acceptance.md",
                "RELEASE.md",
            )
        )
        for term in (
            "engineering evidence",
            "content evidence",
            "visual evidence",
            "real-reading evidence",
            "contact_sheet_review",
            "缩略图总览",
            "human/model visual review",
            "never automatic proof",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_v011_single_coordinator_and_metrics_contract_is_explicit(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/production-workflow.md",
                "references/review.md",
                "references/acceptance.md",
            )
        )
        for term in (
            "single-coordinator",
            "单一协调器",
            "max_in_flight",
            "不等于真实并行",
            "metrics",
            "wall_clock_ms",
            "image_artifact_span_ms",
            "model_wait_ms",
            "image_generation_calls",
            "attempts",
            "failures",
            "retries",
            "rework_rounds",
            "cache_hits",
            "resume_events",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_v011_release_keeps_one_preview_scope_without_audio_video_or_search(self) -> None:
        release = read("RELEASE.md")
        for term in (
            "0.11.0-preview",
            "v0.11.0-preview",
            "schema_version: 1",
            "教育目标卡",
            "音频",
            "视频",
            "搜索 Skill",
        ):
            with self.subTest(term=term):
                self.assertIn(term, release)


    def test_page_manifest_template_exposes_private_production_reference_slot(self) -> None:
        template = json.loads(read("assets/page-manifest-template.json"))
        page = template["pages"][0]

        self.assertEqual(
            page["production_reference_path"],
            "characters/core-v1.2/reference/core-character-assets-v1.2.png",
        )

    def test_first_use_templates_bind_pure_image_core_v12_contract(self) -> None:
        project = json.loads(read("assets/project-template.json"))
        self.assertEqual(project["output_mode"], "pure-images")
        self.assertEqual(project["social_profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(
            project["social_canvas"],
            {"width_px": 1080, "height_px": 1440, "source_aspect_ratio": "3:4"},
        )
        self.assertEqual(project["final_output_contract"], "pure-image-delivery-v1")
        self.assertEqual(project["pure_image_delivery"]["image_size"], "1080x1440")
        self.assertTrue(project["pure_image_delivery"]["text_is_separate"])
        self.assertFalse(project["pure_image_delivery"]["powerpoint_default"])
        self.assertEqual(project["characters_version"], "core-v1.2")
        self.assertEqual(project["characters_path"], "characters/core-v1.2")
        self.assertNotIn("printing", project)

        manifest = json.loads(read("assets/page-manifest-template.json"))
        page = manifest["pages"][0]
        self.assertEqual(page["characters_version"], "core-v1.2")
        self.assertEqual(
            page["character_reference_path"],
            "characters/core-v1.2/reference/core-character-assets-v1.2.png",
        )
        self.assertNotIn("characters/v1", json.dumps(page, ensure_ascii=False))

        book = json.loads(read("assets/book-template.json"))
        self.assertEqual(book["output_mode"], "pure-images")
        self.assertEqual(book["social_profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(book["final_output_contract"], "pure-image-delivery-v1")
        for legacy_print_field in (
            "page_mm",
            "safe_margin_mm",
            "target_dpi",
            "quality_profile",
            "quality_approval",
        ):
            with self.subTest(legacy_print_field=legacy_print_field):
                self.assertNotIn(legacy_print_field, book)

    def test_default_workflow_dependencies_exist_are_tracked_and_importable(self) -> None:
        required_paths = (
            "scripts/build_pure_image_delivery.py",
            "scripts/production_timing.py",
            "scripts/render_social_book.py",
            "scripts/accept_social_book.py",
            "scripts/content_gate.py",
            "scripts/migrate_social_only_layout.py",
            "references/research-input-gate.md",
            "assets/characters/core-v1.2/manifest.json",
            "assets/characters/core-v1.2/manifest-receipt.json",
            "assets/characters/core-v1.2/reference/core-character-assets-v1.2.png",
        )
        for relative_path in required_paths:
            with self.subTest(relative_path=relative_path):
                path = SKILL_DIR / relative_path
                self.assertTrue(path.is_file(), relative_path)

                repository_root = SKILL_DIR.parent
                if (repository_root / ".git").exists():
                    repository_path = f"{SKILL_DIR.name}/{relative_path}"
                    tracked = subprocess.run(
                        ["git", "ls-files", "--error-unmatch", repository_path],
                        cwd=repository_root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(
                        tracked.returncode,
                        0,
                        f"{relative_path} must be present in the clean Git tree",
                    )

        scripts_dir = SKILL_DIR / "scripts"
        sys.path.insert(0, str(scripts_dir))
        try:
            for module_name in (
                "build_pure_image_delivery",
                "production_timing",
                "render_social_book",
                "accept_social_book",
                "content_gate",
                "migrate_social_only_layout",
            ):
                with self.subTest(module_name=module_name):
                    self.assertIsNotNone(importlib.import_module(module_name))
        finally:
            sys.path.remove(str(scripts_dir))

    def test_queue_init_is_documented_as_structural_not_content_gate(self) -> None:
        workflow = read("references/production-workflow.md")
        self.assertIn("generation_queue.py init", workflow)
        self.assertIn("之前", workflow)
        self.assertIn("不会替代", workflow)
        self.assertIn("结构输入", workflow)
        self.assertNotIn(
            "`generation_queue.py init` 必须拒绝创建任务",
            workflow,
        )


    def test_docs_limit_deterministic_checks_to_record_and_file_validation(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/review.md",
                "references/acceptance.md",
            )
        )

        self.assertIn("deterministic gates", combined)
        self.assertIn("never automatic proof", combined)
        self.assertIn("science/story consistency", combined)

    def test_research_gate_guidance_is_explicit(self) -> None:
        skill = read("SKILL.md")
        gate = read("references/research-input-gate.md")
        for term in (
            "research_packet.md",
            "sources.json",
            "claims.json",
            "child_concepts.json",
            "allowed_knowledge",
            "uncertain",
            "pending_confirmation",
            "story-claim trace",
            "unverified_scientific_claim",
            "science_visual_checks",
            "A — input blocked",
            "B — knowledge passed",
            "C — production checked",
        ):
            with self.subTest(term=term):
                self.assertIn(term, skill + gate)

    def test_page_manifest_contract_and_final_acceptance_order_are_structural(self) -> None:
        records = read("references/page-records.md")
        acceptance = read("references/acceptance.md")

        self.assertIn(
            "每页保存正文版本、角色版本、稳定的 `character_reference_path`",
            records,
        )
        self.assertIn(
            '`previous_page_state`、`current_page_entry` 和 `next_page_hook` 都是且仅是 '
            '`{"state_id":"稳定状态标识","summary":"可核对的本页状态说明"}`',
            records,
        )
        self.assertIn(
            "相邻页中前页 `next_page_hook.state_id` 必须等于后页 "
            "`current_page_entry.state_id`",
            records,
        )
        self.assertIn(
            '`text_image_match` 和 `continuity_review` 都是且仅是 '
            '`{"status":"pending|passed|failed","evidence":"实际观察的证据"}`',
            records,
        )
        self.assertIn("不改 schema_version", records)
        self.assertIn(
            "当前新册最终顺序是：运行 `render_social_book.py` 到新的版本目录",
            acceptance,
        )

    def test_agent_metadata_avoids_unsupported_api_product(self) -> None:
        metadata = read("agents/openai.yaml")
        self.assertNotIn("\n  - api\n", metadata)

    def test_layout_and_social_guidance_contract_is_explicit(self) -> None:
        skill = read("SKILL.md")
        composition = read("references/composition.md")
        art_direction = read("references/art-direction.md")
        printing = read("references/printing.md")
        acceptance = read("references/acceptance.md")
        social = read("references/social-output.md")
        combined = "\n".join(
            (skill, composition, art_direction, printing, acceptance, social)
        )

        for term in (
            "layout_design",
            "scene-integrated",
            "soft-card",
            "narrative-band",
            "图像不得生成文字",
            "生成前锁定文字安全区",
            "layout_review",
            "social-vertical-9x16",
            "1080×1920",
            "技术分层",
            "视觉融合",
            "不能声称自动审美通过",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

        self.assertIn("layout_design", skill)
        self.assertIn("layout_review", acceptance)
        self.assertIn("social-vertical-9x16", social)

    def test_social_guidance_requires_portrait_full_bleed_and_in_scene_text(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/composition.md",
                "references/social-output.md",
            )
        )

        for term in (
            "portrait-full-bleed",
            "text_placement",
            "in-scene",
            "禁止横向条幅",
            "禁止底部通栏",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_social_only_guidance_defines_one_xiaohongshu_output(self) -> None:
        skill = read("SKILL.md")
        readme = read("README.md")
        rubric = read("evals/rubric.md")
        composition = read("references/composition.md")
        art_direction = read("references/art-direction.md")
        printing = read("references/printing.md")
        acceptance = read("references/acceptance.md")
        social = read("references/social-output.md")
        combined = "\n".join(
            (skill, readme, rubric, composition, art_direction, printing, acceptance, social)
        )

        for term in (
            "output_mode: pure-images",
            "明确要求可阅读图文",
            "render_social_book.py",
            "当前唯一新输出",
            "xiaohongshu-feed-3x4",
            "1080×1440",
            "小红书静态图文",
            "不能把横向图塞入竖屏",
            "补大块空白",
            "不直接缩放",
            "中心裁切",
            "`social_pages` 每条记录必须包含独立的 `layout_review`",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

        for template_path in (
            "assets/page-manifest-template.json",
            "assets/book-template.json",
        ):
            template = json.loads(read(template_path))
            social_layout = template["pages"][0]["layout_design"]["social_layout"]
            self.assertEqual(social_layout["profile"], "xiaohongshu-feed-3x4")
            self.assertEqual(
                social_layout["canvas"], {"width_px": 1080, "height_px": 1440}
            )
            self.assertEqual(social_layout["source_aspect_ratio"], "3:4")
            self.assertEqual(
                social_layout["subject_safe_area"], [0.50, 0.20, 0.42, 0.54]
            )
            self.assertEqual(
                social_layout["text_safe_area"], [0.08, 0.12, 0.38, 0.24]
            )
            self.assertEqual(
                social_layout["composition_mode"], "portrait-full-bleed"
            )
            self.assertEqual(social_layout["text_placement"], "in-scene")
            self.assertEqual(template.get("output_mode"), "pure-images")

    def test_social_image_generation_requires_native_ratio_preflight(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/social-output.md",
                "references/acceptance.md",
            )
        )

        for term in (
            "preflight_image_generation.py",
            "image_generation_blocked",
            "实际尺寸",
            "不能缩放、中心裁切或补白",
            "先生成一张探针图",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_layout_v1_guidance_requires_measured_cjk_typesetting_and_blocking(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/social-output.md",
                "references/production-workflow.md",
            )
        )
        for term in (
            "字形宽度",
            "标点行首",
            "text_safe_area_candidates",
            "有限字号",
            "排版阻断",
            "文字密度",
            "只报告",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_asset_bound_social_contract_is_structurally_documented(self) -> None:
        skill = read("SKILL.md")
        workflow = read("references/production-workflow.md")
        records = read("references/page-records.md")
        acceptance = read("references/acceptance.md")
        release = read("RELEASE.md")
        combined = "\n".join((skill, workflow, records, acceptance, release))

        for term in (
            "core-v1.2",
            "CHAR-GIRL-01",
            "CHAR-BOY-01",
            "CHAR-MOTHER-01",
            "asset-bound-page-v1",
            "page-production-template.json",
            "page-production-registry.json",
            "style_master.json",
            "manifest-receipt.json",
            "--strict-assets",
            "schema_version: 1",
            "GENERATION_FAILED",
            "不包含音频、视频",
            "新的付费图像接口",
            "真实并行图像调用承诺",
            "一套小红书3:4静态图文",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

        production_template = json.loads(read("assets/page-production-template.json"))
        self.assertEqual(
            production_template["production_schema"], "asset-bound-page-v1"
        )
        self.assertEqual(
            production_template["characters"][0]["character_id"], "CHAR-GIRL-01"
        )

        manifest_template = json.loads(read("assets/page-manifest-template.json"))
        page = manifest_template["pages"][0]
        self.assertEqual(page["production_schema"], "asset-bound-page-v1")
        self.assertEqual(page["profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(page["declared_aspect_ratio"], "3:4")

        book_template = json.loads(read("assets/book-template.json"))
        self.assertEqual(book_template["output_mode"], "pure-images")
        self.assertEqual(book_template["social_profile"], "xiaohongshu-feed-3x4")
        self.assertEqual(
            book_template["social_canvas"],
            {"width_px": 1080, "height_px": 1440, "source_aspect_ratio": "3:4"},
        )

    def test_formal_evals_include_verified_layout_pressure_cases(self) -> None:
        prompts = read("evals/prompts.csv")
        rubric = read("evals/rubric.md")

        for case_id in (
            "layout_natural_whitespace",
            "layout_complex_background",
            "layout_long_copy",
            "layout_whole_book_one_shot",
            "layout_skip_visual_review",
        ):
            with self.subTest(case_id=case_id):
                self.assertIn(case_id, prompts)

        self.assertIn("baseline", rubric)
        self.assertIn("不能把 baseline 结果", rubric)

    def test_phase1_default_flow_is_single_and_explicitly_branched(self) -> None:
        skill = read("SKILL.md")
        workflow = read("references/production-workflow.md")
        combined = "\n".join((skill, workflow))

        for term in (
            "第一阶段最短路径",
            "输入契约 → 知识门禁 → 故事/整本分镜 → 资产锁定",
            "一次整本 strict 预检",
            "一页一次轻量检查",
            "默认不进入 PDF、打印、社媒渲染、历史迁移",
            "按需分支",
            "历史兼容分支",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

    def test_phase1_resume_path_reads_minimum_context_and_has_replan_triggers(self) -> None:
        workflow = read("references/production-workflow.md")
        for term in (
            "续做最小读取集",
            "项目摘要",
            "当前页任务",
            "有效预检回执",
            "当前页队列状态",
            "研究内容、年龄档、故事、页数",
            "单页提示词或单页资产变化只使当前页失效",
        ):
            with self.subTest(term=term):
                self.assertIn(term, workflow)

    def test_phase1_module_ownership_is_explicit(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "SKILL.md",
                "references/production-workflow.md",
            )
        )
        for term in (
            "项目契约",
            "knowledge whitelist",
            "asset registry",
            "page manifest",
            "generation queue",
            "delivery manifest",
            "review/acceptance",
        ):
            with self.subTest(term=term):
                self.assertIn(term, combined)

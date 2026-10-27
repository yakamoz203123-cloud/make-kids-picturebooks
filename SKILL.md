---
name: make-kids-picturebooks
description: Use when the user provides an adult knowledge book or chapter, or only a science, mathematics, economics, physics, chemistry, or engineering topic, and wants an original illustrated picturebook for a selected age band (3–4, 5–7, or 8–10), including age-appropriate topic selection, chapter-limited adaptation, or continuation and revision of an existing knowledge-picturebook project. Do not use for layout or printing of an already-written manuscript without adaptation.
---

# 宝宝知识绘本

把可靠知识改编为适龄原创故事、可观察画面和可追溯生产包。默认交付是 `pure-images`：无字逐页 PNG、独立正文和审核证据；可阅读图文、PDF、打印和社媒版式只有在用户明确要求时启用。

## 默认主链

```text
输入契约 → 章节锁定快照 → 知识门禁 → 故事设计 → 故事/整本分镜 → 资产锁定
→ 一次整本 strict 预检 → 用户授权 → 串行逐页生图
→ 页面审核 → 局部返工 → pure-images 确定性交付
```

默认不进入 PDF、打印、社媒渲染、历史迁移、发布打包或完整性能统计。每个阶段只新增一种结果；关键输入未变时复用证据，不重复整本工作。

`SKILL.md` 只负责入口和路由；[references/production-workflow.md](references/production-workflow.md) 是默认流程唯一详细来源。输入选择统一读取 [references/input-selection.md](references/input-selection.md)，研究门禁读取 [references/research-input-gate.md](references/research-input-gate.md)，其他 reference 按当前分支加载。

默认效率规则：先锁定本章输入和资产版本，再只运行一次整本 `pre_generation/strict`。对外使用 `workflow.py doctor` 这一条入口；终端只输出紧凑门禁摘要，完整 evidence 只有在明确指定 `--report-json` 时保存。独立检查可以共享同一只读快照并并行调度，但不新增第二套验证系统；预检不会修复文件、创建队列或调用图片模型。

## 唯一职责

项目契约负责来源、年龄、输出模式、隐私和授权；knowledge whitelist 负责允许使用的事实；故事/分镜负责教育目标、视觉事件和页面任务；asset registry 负责角色、画风、参考图和版本；page manifest 负责页面约束；generation queue 负责领取、候选、失败和恢复；delivery manifest 负责源图、派生图、哈希和交付关系；review/acceptance 负责内容、视觉、阅读和发布结论。

## 三个日常入口

默认使用 `scripts/workflow.py`：

```text
workflow.py doctor  /absolute/project b01 --version v1
workflow.py resume  /absolute/project b01 --version v1
workflow.py resume  /absolute/project b01 --version v1 --approval "用户批准继续生成下一页" --max-calls 1
workflow.py deliver /absolute/project b01 /absolute/project/books/b01/v1/delivery/pure-image-delivery-v1 --version v1
```

`doctor` 只读检查；`resume` 初始化或复用队列并最多领取一页，正式模式默认开启视觉审核门禁；没有授权返回 `authorization_required`，不会自动批准；`deliver` 委托现有 `pre_delivery/strict` 和人工审核边界。运行中的页面、未知请求、失败页和发布阻断都停止等待下一步，不自动恢复或重试。图片调用的本地保护时限为 180 秒；达到时限只触发只读 `generation_queue.py deadline` 探针，不代表后端失败。

## 不可删除的硬约束

- 默认使用 `output_mode: pure-images`、`pure-image-delivery-v1`、`xiaohongshu-feed-3x4` 和原生 `1080×1440`；保留原图与派生图、路径、尺寸和 SHA-256。
- 生图默认串行，一次只提交一页；`max_in_flight` 不是图片模型并发许可，也不等于真实并行；不自动生成多套备选。
- 不接入新的付费图像接口，不通过提高并发换取表面速度。
- 队列只负责缓存、失败记录、断点续跑和 `reset-page`，不调用图片 API，不代替内容门禁。
- `pending` 不等于 `approved`；脚本是 deterministic gates，`never automatic proof`。
- 用户授权、真实儿童隐私、版本化角色/画风、来源边界和 `schema_version: 1` 兼容性不可省略。

## 输入、故事与资产

使用 `references/input-selection.md` 选择年龄和主题；使用 Research 包时先运行 `content_gate.py validate-packet` 生成 `knowledge-whitelist.json`，故事完成后运行 `content_gate.py validate-story` 并保留 `story-claim trace`。教育目标卡必须在正式分镜前填写 `core_knowledge`、`target_age_band`、`prior_experience`、`visible_relationship`、`knowledge_boundary` 和 `reading_observation`。新故事先读取 [references/story-design.md](references/story-design.md)，完成最小故事卡和故事门禁，再进入正文与整本分镜。

先故事、再页面、再镜头；采用视觉事件驱动分页，页数自主决定。正文中的多个重要动作或知识事件应删减、拆分或重新安排，形成“儿童行动—期待—发现”，不能只排成观察说明清单。角色身份锁定、系列角色优先、规范角色名、别名/同音字解析和 approved/reused 版本见 [references/characters.md](references/characters.md)。

复用已批准且带版本号的 character bible、`character_reference_path`、`production_reference_path` 和画风；默认资产包是 `core-characters-v1.2`，遵循“约 80% 固定资产、约 20% 页面变化”，首次资产或画风试样等待确认。真实儿童只在私有项目使用，遵守 `privacy_scope`/`public_release`，不进入 Skill 仓库或 GitHub。

快速出图协议：先完成 `layout_design` 和目标 profile 预检，再调用图像生成器；使用稳定基础提示词、同版本 `production_reference_path`，每页一次生成，先检查已有结果，不重复提交。历史“两页一批”只是兼容记录，不代表并行许可。

生图调用必须有明确的本地保护边界：请求开始后 180 秒内可继续等待；超过 180 秒先运行 `generation_queue.py deadline QUEUE_JSON --request-id REQUEST_ID`，检查目标产物；无产物时严格按 `timeout-request → pending-unknown → 停止` 处理，不自动重试或领取下一页。

## 门禁、页面和证据

正式生图前运行 `workflow.py doctor ... --mode strict`；需要完整证据时加 `--report-json`。其内部复用 `project_preflight.py ... --phase pre_generation --mode strict`，正式 `generation_queue.py init` 会复验并保存回执。页面继续保留 manifest continuity fields：`previous_page_state`、`current_page_entry`、`next_page_hook`、`state_id`、`summary`、`continuity_invariants` 和 `visual_direction`。`page-manifest` 是页面约束和科学证据的事实源。

`doctor` 的 `READY_FOR_USER_AUTHORIZATION` 只表示工程和内容门禁满足进入生图阶段的条件，不代表已获得用户授权，也不代表人工视觉审核通过；`HOLD`、`STALE`、`NEEDS_REVIEW` 或任一 blocker 都必须停止。预检结果中的 `image_generation` 应保持 `SKIPPED`，直到用户明确授权并进入队列。

审核必须观察 `layout_review`、`text-image state matching` 和 `adjacent-page pair`；页面字段和审核记录分别见 [references/page-records.md](references/page-records.md) 与 [references/review.md](references/review.md)。技术生成成功、尺寸通过和脚本通过都不等于人工视觉批准。交付顺序默认是 `build_pure_image_delivery.py` 后由人工批准，再由 `release_pure_image_delivery.py` 释放；四类证据分别是 `engineering evidence`、`content evidence`、`visual evidence` 和 `real-reading evidence`。

## 按需分支

- 可阅读图文：读取 `references/composition.md`、`references/social-output.md`，使用 `render_social_book.py`、`render_social.py`、`accept_social_book.py`；图像不得生成文字，必须检查文字安全区和 `layout_review`。
- PDF/打印：读取 `references/printing.md`、`references/acceptance.md`，按需使用 `export_book.py`、`validate_exports.py`、`acceptance` 或 `impose_booklet.py`。
- 历史迁移、归档、性能诊断和发布打包只在明确请求时启用。

续做只读取项目摘要、当前页任务/依赖、有效预检回执和队列状态。研究、年龄档、故事、页数、关键角色/画风、连续性契约、输出模式或预检规则变化时重新跑整本 strict；单页提示词或资产变化只使当前页失效，只重新生成该页。

只记录真实可观测的总耗时、图像产物跨度、模型等待、生成调用、失败、返工、缓存命中、断点恢复和输出质量；不可观测值写 `unknown`。

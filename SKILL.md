---
name: make-kids-picturebooks
description: Use when the user provides an adult knowledge book or chapter, or only a science, mathematics, economics, physics, chemistry, or engineering topic, and wants an original illustrated picturebook for a selected age band (3–4, 5–7, or 8–10), including age-appropriate topic selection, chapter-limited adaptation, or continuation and revision of an existing knowledge-picturebook project. Do not use for layout or printing of an already-written manuscript without adaptation.
---

# 宝宝知识绘本

本 Skill 把可靠知识改编为适龄原创故事、可观察的科学画面和可追溯的插画工作包。默认交付是 `pure-images`：逐页无字 PNG、独立可编辑正文和审核证据。明确要求可直接阅读的图文绘本时，才沿用现有图文渲染入口，并保留无字源图。

## 第一阶段最短路径

默认新项目只走这一条主链路：

```text
输入契约 → 知识门禁 → 故事/整本分镜 → 资产锁定
→ 一次整本 strict 预检 → 串行逐页生图
→ 页面审核 → 失败页局部返工 → pure-images 确定性交付
```

默认不进入 PDF、打印、社媒渲染、历史迁移、发布打包或完整性能统计；这些是按需分支或历史兼容分支。不要因为脚本存在就自动启用它们。

每个阶段只新增一种结果；已完成且关键输入未变的证据直接复用。技术生成成功、尺寸通过和预检通过，都不等于人工视觉通过或最终发布批准。

## 模块职责

| 模块 | 唯一职责 |
|---|---|
| 项目契约 | 来源、年龄、输出模式、隐私范围和用户授权 |
| knowledge whitelist | 允许使用的事实 |
| 故事/分镜产物 | 教育目标、故事、视觉事件和页面任务 |
| asset registry | 角色、画风、参考图和版本 |
| page manifest | 当前页面的生产约束 |
| generation queue | 领取、提交、候选、失败和恢复状态 |
| delivery manifest | 源图、派生图、哈希和交付文件关系 |
| review/acceptance | 内容、视觉、阅读和发布结论 |

`SKILL.md` 负责入口、边界和路由；[references/production-workflow.md](references/production-workflow.md) 是默认生产流程的唯一详细来源。其他 reference 只在当前分支需要时读取。

## 统一操作入口

为了减少需要记忆的内部命令，默认优先使用 `scripts/workflow.py` 的三个动作；它只是编排层，不复制或绕过底层门禁：

```text
python3 "$SKILL_DIR/scripts/workflow.py" doctor /absolute/project b01 --version v1
python3 "$SKILL_DIR/scripts/workflow.py" resume /absolute/project b01 --version v1
python3 "$SKILL_DIR/scripts/workflow.py" resume /absolute/project b01 --version v1 --approval "用户批准继续生成下一页" --max-calls 1
python3 "$SKILL_DIR/scripts/workflow.py" deliver /absolute/project b01 /absolute/project/books/b01/v1/delivery/pure-image-delivery-v1 --version v1
```

`doctor` 只读检查项目；`resume` 初始化或复用队列并最多领取一页，没有明确授权时只返回 `authorization_required`，不会自动批准；`deliver` 委托现有 `pre_delivery/strict` 和人工审核边界。遇到运行中的页面、未知请求、失败页或发布阻断时，入口会停止并给出下一步，不自动恢复或重试。需要详细证据、历史兼容或诊断时，仍可直接使用各底层脚本。

## 不变的质量和安全契约

- 默认新输出使用 `output_mode: pure-images`、`pure-image-delivery-v1`、`xiaohongshu-feed-3x4` 基础画布契约和原生 `1080×1440`；这里的 profile 只规定源图比例与画布，不表示默认渲染社媒文字。
- 原始生成图与最终交付图分开保存。比例正确但为 `1086×1448` 的原图不是原生 `1080×1440`；可以由 `build_pure_image_delivery.py` 生成独立派生图，但必须保留源/派生路径、尺寸和 SHA-256，不覆盖原图。
- 生图默认串行，一次只提交一页。`max_in_flight` 不是图片模型并发许可，也不等于真实并行；默认生产不使用 2—3 的兼容领取上限。
- 队列不调用图片 API，也不把任务状态当作内容门禁；它只负责缓存、失败记录、断点续跑和 `reset-page`。
- 不接入新的付费图像接口，不提高并发量，不自动生成多套备选。
- 真实儿童资料只放在私有项目，记录 `privacy_scope`/`public_release`，不进入 Skill 仓库或 GitHub。
- `pending` 不等于 `approved`；脚本是 deterministic gates，`never automatic proof`。
- 不改变历史项目的输出契约、正式角色、画风、候选原图或 `schema_version: 1`。

## 1. 知识门禁和年龄边界

入口可以是成人知识书籍/章节，也可以是科学、数学、经济学、物理、化学或工程主题。主题入口先使用 `kids-knowledge-research` 研究包和事实追溯；研究 Skill 只负责可靠知识发现和研究包，不负责创作。

使用 Research 包时读取 [references/research-input-gate.md](references/research-input-gate.md)，运行 `content_gate.py validate-packet`，生成版本化 `knowledge-whitelist.json`。`uncertain`、`pending_confirmation` 和 `omit` 不得作为儿童事实；故事完成后运行 `content_gate.py validate-story` 并保留 `story-claim trace`。

当前已验证的主题研究上游只覆盖 3—4 岁。5—7 或 8—10 岁只给主题时，必须提供成人知识来源或已审研究包，不能静默套用 3—4 岁研究结果。

教育目标卡必须在正式分镜前包含 `core_knowledge`、`target_age_band`、`prior_experience`、`visible_relationship`、`knowledge_boundary` 和 `reading_observation`；模板见 `assets/education-goal-template.json` 和 [references/education-goals.md](references/education-goals.md)。

## 2. 故事、分镜和页面任务

创作顺序固定为**先故事、再页面、再镜头**。先锁定主角愿望、行动、变化、疑惑、理解和结尾，再提取视觉事件；不要先按固定 8、12 或 16 页填内容。

故事编辑开始前做**角色身份锁定**：系列角色优先，使用规范角色名、角色 ID、别名/同音字映射和 approved/reused 版本。新角色必须在正式分镜前绑定角色档案、参考图和服饰策略。

分页采用**视觉事件驱动分页**：如果删除一页对故事、知识和情绪几乎没有影响，可以删除、合并、拆分或调整页面；如果一页包含不同时间的关键动作，优先拆分。页数由故事和视觉事件自主决定。

正文中的多个重要动作或知识事件不能只靠一张静态图同时承担，应在故事阶段删减、拆分或重新安排。每个关键科学变化要形成“儿童行动—期待—发现”，不能只排成观察说明清单。

分镜先完成整本视觉节奏，再选逐页镜头。每页一个主要视觉任务，写清故事任务、视觉主角、第一眼信息、关键动作、科学证据、构图理由和文字安全区；完成后做相邻页重复审计，只保留有价值的重复。

页面继续保留 manifest continuity fields：`previous_page_state`、`current_page_entry`、`next_page_hook`、`state_id`、`summary`、`continuity_invariants` 和 `visual_direction`。这些字段传递约束，不替代真实生图后的科学、连续性和审美审核。

## 3. 角色、画风与资产

复用已批准且带版本号的 character bible、`character_reference_path`、`production_reference_path` 和画风。首次资产或画风试样等待人工确认；真实儿童角色必须遵守私有资料边界。资产注册表负责版本和哈希，page manifest 只记录当前页使用哪些资产。页面或资产失败保留机器可读 failure code，例如 `MISSING_ASSET`、`REFERENCE_NOT_FOUND`、`INVALID_DIMENSIONS`、`ASPECT_RATIO_MISMATCH` 和 `GENERATION_FAILED`。角色资产遵循“约 80% 固定资产、约 20% 页面变化”：固定角色身份、比例、画风和已选资产，页面只描述场景、道具、知识证据、构图、安全区和连续性变化。

版本事实源是 `assets/style-registry.json`：默认 `STYLE-CORE-01:v1.2` 使用 `core-characters-v1.2`；已正式发布的 `STYLE-06:v0.1` 才显式使用 `core-characters-v1.3`。v1.3 不是全局默认，不能因为资产包已发布就替换历史默认角色与画风。

快速出图协议是：先完成 `layout_design` 再调用图像生成器；稳定基础提示词只保留画风、角色不变特征、目标比例、全局禁项和文字安全区；正式参考图使用 `production_reference_path`；每页一次生成；先检查已有结果，不要重复提交。历史“两页一批”仅为兼容记录，不代表并行许可。

## 4. 门禁、生产和审核

规划、资产解析和 `layout_design` 完成后，在第一张正式图片提交前运行一次 `project_preflight.py ... --phase pre_generation --mode strict`。预检是只读的，不调用图片模型；正式项目的 `generation_queue.py init` 会自动复验同一 strict 门禁并保存 `preflight_receipt`，门禁不通过时不创建或改写队列。没有 `project.json` 的低层独立队列默认被 CLI 拒绝；只有明确进行历史兼容测试时才加 `--standalone-legacy`。队列不会替代 Research、教育目标、内容、strict-assets 或比例检查，只验证结构输入并绑定门禁结果。

逐页只做一页一次轻量检查、一次授权调用、候选隔离、尺寸/路径/SHA-256 校验和页面审核。生产队列必须先记录有限次数的用户生成授权，`claim` 消费授权 ID；超时或 `pending_unknown` 立即停止，未经新授权不得自动恢复、重试或领取下一页。

页面审核保留 `layout_review`、`text-image state matching` 和 `adjacent-page pair`。最终分别记录图片工具返回成功、技术规格通过、人工视觉审核通过和最终发布批准。四类证据互不替代：`engineering evidence`、`content evidence`、`visual evidence`、`real-reading evidence`。
`build_pure_image_delivery.py` 只产生技术交付包，`release_status` 保持 `human_review_pending`；通过 `pre_delivery/strict` 和项目最终审核后，再运行 `release_pure_image_delivery.py` 写入 `release-receipt.json`。技术构建成功不等于正式发布。

## 5. 按需分支和历史兼容分支

- 明确要求可阅读图文成品时，读取 [references/composition.md](references/composition.md)、[references/social-output.md](references/social-output.md)，使用 `render_social_book.py`、`render_social.py` 和 `accept_social_book.py`。必须使用真实字形宽度、文字安全区和 `layout_review`；图像不得生成文字，禁止横向条幅，禁止底部通栏。
- 可阅读图文排版按真实字体字形宽度换行；字号只能在有限字号范围内调整，无法放入安全区时记录排版阻断，不删除或改写正文。
- 明确要求 PDF/打印时，读取 [references/printing.md](references/printing.md) 和 [references/acceptance.md](references/acceptance.md)，使用 `export_book.py`、`validate_exports.py`、`acceptance` 或 `impose_booklet.py`。这是历史兼容分支，不是默认成品路径。
- 历史社媒迁移、性能诊断、归档和发布打包只在明确请求或诊断需要时启用。

默认入口按需读取 [references/characters.md](references/characters.md)、[references/page-records.md](references/page-records.md)、[references/review.md](references/review.md) 和 [references/acceptance.md](references/acceptance.md)。

## 6. 续做与重新规划

续做已有多页项目只读取 `project_state.py` 摘要、当前页任务、当前页依赖资产、有效 strict 回执和队列状态；不要重复 Research、完整故事验证、全部页面审计、整本测试或全量资产哈希。

研究内容、年龄档、故事、页数、关键角色/画风、连续性契约、输出模式或预检规则变化，或无法证明关键输入未变时，重新运行一次整本 strict。单页提示词或单页资产变化只使当前页失效，只重建当前页，之后只重新生成该页。

## 7. 可观测指标

只记录真实可观测的 `wall_clock_ms`、`image_artifact_span_ms`、`model_wait_ms`、`image_generation_calls`、`attempts`、`failures`、`retries`、`rework_rounds`、`cache_hits`、`resume_events` 和 `output_quality`。不可观测值写 `unknown`，不能把没有日志写成零。

用户可以用一句话开始或继续：“从实际来源制作/继续一套适合 X 岁的儿童知识绘本，沿用已批准角色与画风；按当前授权继续生产。”

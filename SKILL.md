---
name: make-kids-picturebooks
description: Use when the user provides an adult knowledge book or chapter, or only a science, mathematics, economics, physics, chemistry, or engineering topic, and wants an original illustrated picturebook for a selected age band (3–4, 5–7, or 8–10), including age-appropriate topic selection, chapter-limited adaptation, or continuation and revision of an existing knowledge-picturebook project. Do not use for layout or printing of an already-written manuscript without adaptation.
---

# 宝宝知识绘本

本 Skill 把可靠知识改编为适龄原创故事、可观察的科学画面和可追溯的插画工作包。默认交付 `pure-images`：逐页无字 PNG，正文作为独立可编辑文本；明确要求可直接阅读的图文绘本时，沿用现有图文渲染入口把正文嵌入画面，并同时保留无字源图。两种交付共用同一套研究、内容、资产、预检、队列和审核证据；不得静默改变历史项目的输出契约。若现有项目配置与用户要求不一致，先报告差异并保持待批准，不直接改写历史配置。不默认生成 PowerPoint、PDF、打印拼版、9:16 或多套候选。

## V1.1 契约原则

- `pure-images` 表示无字插画与独立正文；可阅读图文绘本表示正文已经进入画面内部的完整成品。技术生成成功、尺寸通过和预检通过，均不等于人工视觉通过或最终发布批准。
- 原始生成图与最终交付图分开记录。比例正确且来源可核验的 `1086×1448` 原图不是原生 `1080×1440`；可以由现有确定性交付脚本生成独立 `1080×1440` 派生图，但必须保留原图、原图 SHA-256、派生图、派生图 SHA-256、源路径和源/派生尺寸关系。不得把原图标为原生合规，也不得覆盖原图。
- 严格预检只在关键输入未变且回执证据可逐项比较时复用；关键输入改变或无法证明一致时只重新运行一次整本 strict。正常逐页生产不重复研究、全书规划、全量测试或开发探针。
- 生图默认串行：一次只提交一个请求；前一请求取得明确结果后才可继续授权范围内的下一页。`pending_unknown`、超时和其他阻断立即停止；队列的 `max_in_flight` 不是图片模型并发许可。
  - 入口既支持成人知识书籍/章节改编，也支持用户只提供科学、数学、经济学等知识主题；仅给主题时，当前已验证的 `kids-knowledge-research` 上游只覆盖 3—4 岁，5—7 或 8—10 岁必须提供成人知识来源或已审研究包，不能静默套用 3—4 岁研究结果。

## V1.0 核心原则

## 默认生产流程（唯一）

默认生产只有以下8步：知识研究 → 故事编辑 → 整本分镜 → 统一角色和画风资产锁定 → 一次严格生产预检 → 串行逐页生图 → 人工视觉审核 → 确定性交付。每步只有一个主要职责；已完成且输入指纹未变化的证据直接复用，输入或规则变化时只使受影响证据和页面失效。默认路径不进入打印/PDF、社媒阅读渲染、历史迁移、发布打包或完整性能统计；这些能力只在用户明确请求或诊断需要时启用。

## A：整本规划（只做一次）

1. 读取实际来源、继续项目状态和目标年龄；用户已指定单一年龄档时直接沿用。
2. 若使用 Research 包，先读 [references/research-input-gate.md](references/research-input-gate.md)，运行 `content_gate.py validate-packet`，生成版本化 `knowledge-whitelist.json`。`uncertain`、`pending_confirmation`、`omit` 不得作为儿童事实；没有完整包时如实标记追溯边界。
3. 完成教育目标卡、概念卡、完整 `story.md`、全书 `storyboard.json`、逐页正文、`page-manifest.json`、`layout.json` 和页面提示词。教育目标卡在正式分镜前必须有 `core_knowledge`、`target_age_band`、`prior_experience`、`visible_relationship`、`knowledge_boundary`、`reading_observation`；完整故事完成后运行 `content_gate.py validate-story` 和 `story-claim trace` 检查。
4. 复用已批准且带版本号的 character bible、`character_reference_path`、`production_reference_path` 和画风；首次资产或画风试样仍须等待人工确认。页面记录必须保留 manifest continuity fields：`previous_page_state`、`current_page_entry`、`next_page_hook`，每项使用稳定 `state_id` 和可核对的 `summary`。
5. 由 Codex 从故事、教育目标、分镜、科学视觉证据和 continuity invariants 自主选择镜头、构图、角色动作、固定道具、科学状态变化、文字安全区和不合格条件；用户不需要逐页编写提示词。关键科学页优先保证现象可见，过渡页允许人物成为焦点。
6. 规划、资产解析和 `layout_design` 完成后，整本只运行一次必要的 strict 生成前预检。`report-only` 仅用于诊断；预检通过不等于人工视觉或科学批准。预检通过后，内部按需用 `generation_queue.py init` 建立一页一任务记录并申请生图授权；普通用户不需要把队列状态当作默认决策入口。

### V2：故事编辑与整本视觉导演

创作顺序固定为：先故事、再页面、再镜头。研究和教育目标完成后，先明确主角的愿望、行动、变化、疑惑、理解和结尾，再从故事中提取具有独立价值的视觉事件；不要先按固定 8、12 或 16 页填内容。用户指定页数时照办，但指出明显拥挤风险；否则由故事和视觉事件自主决定页数。

故事编辑开始前先做**角色身份锁定**：读取当前项目的 approved/reused character bible、规范角色名、角色 ID、别名映射、版本和稳定外观；系列角色优先，不能把临时昵称、同音字或页面临时描述当成新角色。正文、分镜和提示词统一使用规范角色名，出现别名/同音字时先解析并记录到同一角色，无法解析时阻断故事规划。新角色必须是明确的创作选择，并在正式分镜前绑定 approved/reused/temporary 的角色档案、角色参考和服饰策略；不能只在分镜里临时发明名字、外貌或衣服。该锁定只约束身份与连续性，不修改正式角色图片。

故事初稿必须经过一次整本编辑：检查动机、因果、情绪变化、过度解释、突然结论、重复动作、重复信息和结尾完整性。分页采用**视觉事件驱动分页**：若删掉一页对故事、知识和情绪几乎没有影响，允许直接删除、合并、拆分或调整页面；若一页包含不同时间的关键动作，优先拆分。允许保留安静观察或有价值的重复，但必须写明它服务于比较、停顿或翻页钩子的理由。

故事编辑还要做**正文—视觉事件匹配**：正文中的多个重要动作或知识事件不能只靠一张静态图同时承担；先判断儿童第一眼能否看懂本页的主要事件，再在故事阶段删减、拆分或重新安排，不能把动作冲突推给提示词或排版层。不要机械规定每页固定字符数量，按动作数量、知识关系、情绪转折和文字安全区共同判断。

知识状态不能只排成观察说明清单：每个关键科学变化至少要连接一个儿童的行动、期待或疑惑、可见发现和情绪/理解变化，即形成“儿童行动—期待—发现”的推动链。若删掉主角的行动和发现后页面仍能按时间顺序机械排列，应回到故事阶段重写愿望、阻碍、尝试、发现或结尾；科学顺序和研究边界不得为制造戏剧性而改变。

故事分页后先做**整本视觉节奏**，再逐页选镜头。每页一个主要视觉任务，至少写清故事任务、视觉主角、儿童第一眼看到什么、关键动作、科学证据、景别/构图理由和文字安全区。整本完成后做**相邻页重复审计**：比较主体、站位、动作、景别、视角、情绪和新增信息；连续相似且没有叙事理由时重写、合并或换镜头。科学对照需要保持同一观察对象时，可以保留相似构图，并说明对照价值。

每页可在 storyboard 与 page manifest 中声明可执行的 `visual_direction`：`story_task`、`visual_subject`、`must_show`、`must_not_show`、`visual_result`、`science_evidence`、`composition_reason`。这些字段把“必须出现、不能出现、必须呈现的结果和连续状态”写成任务输入；现有 `page_delta` 与 `continuity_invariants` 继续保留。任务组装会将 storyboard 的 `visual_direction`（无则回退 manifest）放入 `page_task`，但它只证明约束已传递，不替代真实生图后的科学、连续性和审美审核。

正文与画面同步编辑：画面已能表达的信息不重复解释；对白和知识句保持短；如果文字无法自然放入安全区，在故事阶段删减、改写或拆页，不能把问题推给排版层。3—4 岁的文字密度检查只报告，不自动改写正式正文。

## B：受控生图（继续项目时只走本阶段）

继续已有绘本时先读取项目简要状态和目标页任务；只有已有多页项目或断点恢复需要时才读取队列状态。若严格预检回执仍有效，只做当前页轻量检查：页面指纹、必要提示词、角色/画风版本与哈希、`continuity_task.prompt_addendum`、输出路径隔离和用户授权。不要重新运行研究、完整故事验证、全部页面审计、整本测试或全量资产哈希。

**快速出图协议**：先完成 `layout_design` 再调用图像生成器；稳定基础提示词只保留画风、角色不变特征、目标比例、全局禁项和文字安全区，每页只追加短的场景动作、道具、知识证据及前后页状态。正式参考图使用 `production_reference_path`。默认每页一次生成、一次只提交一页；用户可以一次授权多页和最大调用次数，但前一页必须取得明确结果后才能提交下一页。旧流程的“两页一批”只作为历史兼容记录，不代表并行许可。生成器已返回、任务仍运行或输出目录已有文件时先检查已有结果，**不要重复提交**。没有明确失败和输出缺失，不得重试。

队列只负责本地计划、领取、缓存、失败记录、断点续跑和 `reset-page`；它不调用图像 API，也不证明服务端已接受请求。由一个 `single-coordinator`（单一协调器）维护同一队列。宿主生命周期为：

```text
claim
→ 保存 request_id、page_version、revision、attempt
→ 执行一次已授权图片调用
→ 观察到本地提交动作后 mark-submitted
→ 保存候选并校验规格、路径、SHA-256
→ complete 或保持人工审核 pending
```

没有服务端编号写 `backend_task_id=unknown`。超时按 `timeout-request → 检查产物 → pending-unknown → 停止` 处理；未经新授权不得恢复、自动重试或领取下一页。不得把调用开始当作提交成功，也不得把技术生成成功当作人工视觉批准。

## C：整本交付（授权范围完成后）

统一检查图片规格、正文、图文关系、相邻页和整本连续性，再使用现有交付能力生成一版完整成品。`build_pure_image_delivery.py` 默认做确定性复制/规范化、尺寸/哈希/缩略图和校验，并记录源图与派生图关系；明确需要可阅读图文成品时才调用现有图文渲染入口。正文进入画面内部自然留白，不使用默认底部通栏字幕；图像不得生成文字。

验收分开保存 `engineering evidence`、`content evidence`、`visual evidence` 和 `real-reading evidence`，保存逐页 `layout_review`、`text-image state matching`、`adjacent-page pair` 和 `contact_sheet_review`。四道门必须分别记录：图片工具返回成功、技术规格通过、人工视觉审核通过、最终发布批准。脚本是 deterministic gates，`never automatic proof`；角色、科学画面、无字、图文融合和真实共读仍需 human/model visual review。没有真实共读或最终批准时保持 `pending`，不得标记正式发布完成。

## 复用与失效规则

## 自动图文排版 V1.0 最小规则

明确要求可阅读图文成品时，`render_social_book.py` 继续只读取无字源图和正式正文；排版层必须按实际字体的**字形宽度**测量中文换行，不按字符串长度估算。中文逗号、句号、问号、感叹号、分号、顿号和闭引号不得错误地位于**标点行首**或单独成行；保留原文标点、段落和全部正文。

- 文字高度按真实字体高度、行距和实际行数计算；字号只能在有限字号范围内调整。无法在声明的文字安全区内容纳时输出明确的排版阻断，不删除正文、不改写故事、不无限缩小字号、不让文字覆盖人物或科学证据。
- 每页继续使用自己的 `social_layout.text_safe_area`。如需少量候选位置，可增加 `text_safe_area_candidates`；渲染器只根据声明的几何安全区和 `subject_safe_area` 选择不重叠候选，不声称自动识别人脸、人物表情或科学对象。
- 文字框的宽度和高度随实际内容计算；`scene-integrated` 只绘制局部浅色描边/光晕，历史 `soft-card` 也只能包住实际文字加内边距，不使用覆盖整块画面的固定面板。
- 对3—4岁页面可输出轻量**文字密度**提醒（正文较长、行数较多、对话较长），该检查**只报告**，不得自动删改正式正文。密度提醒和脚本通过都不等于人工视觉审核通过。

严格预检回执只有同时满足以下条件才可复用：`status=passed`、阶段为 `pre_generation`、`mode=strict`、`blockers=[]`、`write_operations=0`、`image_model_calls=0`；回执中的 `page_task_assembly.plan_fingerprint`、研究/claim 哈希、批准资产/画风版本及项目契约与当前输入一致。当前页的队列 `request_fingerprint` 或 `asset_dependency_fingerprint` 改变时，只重建该页任务并重新检查该页；故事、研究白名单、关键角色/画风、连续性契约、预检规则或页面数量改变时，重新运行一次整本 strict 预检。若无法证明关键依赖未变，不猜测复用，运行一次预检。

## 固定安全边界与兼容路径

- 缺少实际来源、年龄档、可用图像能力、已确认角色或画风时停止；`pending` 不等于 `approved`。真实儿童资料只放在私有项目，记录 `privacy_scope`/`public_release`，不进入 Skill 仓库或 GitHub。
- 不修改正式角色、画风、历史项目、历史请求或候选原图；候选与正式页隔离；不接入新的付费图像接口，不提高并发量。
- 默认新输出使用 `output_mode: pure-images`、`pure-image-delivery-v1`、`xiaohongshu-feed-3x4` 基础画布契约和原生 `1080×1440`；这里的 profile 只规定源图比例与画布，不表示默认渲染社媒文字。用户明确要求可阅读图文成品时，必须沿用项目已声明的图文渲染契约并另存无字源图。实际比例必须由 `preflight_image_generation.py` 验证；返回横图时记录 `image_generation_blocked` 并停止，不缩放、裁切或补白冒充通过。画内正文必须自然留白，禁止横向条幅、禁止底部通栏和图像内文字。
- 页面新契约使用 `asset-bound-page-v1`；旧 `schema_version: 1` 保持兼容。`validate_page_manifest.py --strict-assets` 是显式附加门禁。失败保留机器可读 `failure_code`，包括 `MISSING_ASSET`、`REFERENCE_NOT_FOUND`、`INVALID_DIMENSIONS`、`ASPECT_RATIO_MISMATCH`、`GENERATION_FAILED`。
- 旧打印分支仅在明确请求时使用 `export_book.py`、`validate_exports.py` 和 `acceptance`；不把打印字段当作当前社媒成品证据。

## 常用入口

```bash
python3 "$SKILL_DIR/scripts/project_state.py" /absolute/project/project.json
python3 "$SKILL_DIR/scripts/content_gate.py" validate-packet /absolute/research-package
python3 "$SKILL_DIR/scripts/content_gate.py" validate-story /absolute/project/story.md /absolute/project/review/story-claim-trace.json /absolute/project/review/knowledge-whitelist.json
python3 "$SKILL_DIR/scripts/project_preflight.py" /absolute/project b01 --version v1 --phase pre_generation --mode strict
python3 "$SKILL_DIR/scripts/generation_queue.py" status /absolute/project/books/b01/v1/review/production-queue.json
python3 "$SKILL_DIR/scripts/build_pure_image_delivery.py" /absolute/project b01 /absolute/project/pure-image-delivery/b01 --version v1
```

默认入口按 [references/production-workflow.md](references/production-workflow.md) 读取轻量页面流程、[references/characters.md](references/characters.md)、[references/page-records.md](references/page-records.md)、[references/review.md](references/review.md) 和 [references/acceptance.md](references/acceptance.md)。构图、社媒阅读、打印/PDF、迁移和发布打包只在明确请求或诊断需要时按需读取 [references/composition.md](references/composition.md)、[references/printing.md](references/printing.md) 等对应参考文件；继续已有多页项目时再读取 `project_state.py` 和队列状态。

用户可以用一句话开始或继续：“从实际来源制作/继续一套适合 X 岁的儿童知识绘本，沿用已批准角色与画风；按当前授权继续生产。”

## 指标

只记录真实可观测数据：`wall_clock_ms`、`image_artifact_span_ms`、`model_wait_ms`、`image_generation_calls`、`attempts`、`failures`、`retries`、`rework_rounds`、`cache_hits`、`resume_events`。不可观测值写 `unknown`，不能把没有日志写成零；分别区分生图前准备时间、工具等待时间和人工审核等待时间。

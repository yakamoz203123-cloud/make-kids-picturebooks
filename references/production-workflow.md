# 单 Skill 的精简生产流程 V1.1

本流程仍由 `make-kids-picturebooks` 一个 Skill 执行。核心路径是“一次整本预检，逐页轻量检查，直接进入已授权生图”；不新建缓存数据库、状态机、队列或审批服务。

## 0.1 交付与尺寸契约

- `pure-images` 是无字插画加独立正文；可阅读图文绘本是把正文合成进画面内部的完整成品。两者共用同一套内容、资产、预检、队列和审核证据。用户明确要求可阅读成品时，走现有图文渲染入口，同时保留无字源图。
- 历史项目的 `output_mode`、布局和交付方式不能被静默改写。若项目配置与本次需求不一致，先记录差异并保持待批准；不要把一次新渲染当成历史项目契约已经改变。
- 原始生成图与最终交付图分开记账。比例正确、来源可核验的 `1086×1448` 原图可以由现有确定性交付脚本生成独立 `1080×1440` 派生图；原图、原图 SHA-256、派生图、派生图 SHA-256、源路径、源尺寸和派生尺寸必须同时保留。`1086×1448` 原图不得标记为原生 `1080×1440`，不得覆盖原图。
- 现有 `build_pure_image_delivery.py` 已支持这种确定性规范化并把源/派生关系写入清单；它不是生图，也不替代 `preflight_image_generation.py` 对实际生成源图的比例检查。正式页和最终成品仍以实际派生图规格为准。

## 0. 基线与计时

改流程前记录已有可观测基线：总耗时、绘图产物跨度、真实模型等待时间、图像生成调用次数、失败/重试/返工次数、缓存命中和输出质量。旧项目缺少任务级日志时写 `baseline_unknown` 或 `unknown`，不能用 `acceptance.errors: []` 推断为零，也不能把历史截图中的31分钟当作可复测基线。

计时至少区分：Codex 规划/文件读取、脚本执行、整本预检、单页任务准备、图片工具等待、人工审核等待和交付排版。性能目标可以写成目标，不得伪造达标。

## 1. 阶段 A：整本规划与一次预检

先完成一次规划：知识门禁 → 教育目标卡 → 概念卡与完整 `story.md` → 全书 `storyboard.json` → `page-manifest.json`/`layout.json` → 角色/画风/生产参考绑定 → 全部页面提示词与科学视觉证据。

规划中的故事编辑顺序是“先故事、再页面、再镜头”：先完成角色身份锁定，优先解析系列角色的规范角色名、`character_id`、别名/同音字和 approved/reused 版本；完成主角动机和因果链后，提取视觉事件，执行视觉事件驱动分页，允许删除、合并、拆分或调整页面，并由故事而不是固定页数决定页数。故事分页通过后，先做整本视觉节奏，再为每页指定一个主要视觉任务；完成分镜后做相邻页重复审计，只有比较需要或翻页节奏需要时才保留有价值的重复。

故事阶段同时检查正文—视觉事件匹配：正文中的多个重要动作或知识事件必须删减、拆分或重新安排，直到单张静态画面能表达本页主要事件；不机械规定固定字符数量。科学状态不能只是观察说明清单，每个关键变化应通过儿童行动—期待—发现推动，并在不改变研究顺序和边界的前提下形成情绪或理解变化。

教育目标卡必须在正式分镜前包含 `core_knowledge`、`target_age_band`、`prior_experience`、`visible_relationship`、`knowledge_boundary`、`reading_observation`。Research 输入包先经过 `content_gate.py`；故事完成后保留 `story-claim trace`。页面任务必须包含角色、固定道具、当前科学阶段、镜头、正文安全区、前后页状态和 `continuity_task.prompt_addendum`。

页面可声明 `visual_direction`，至少包含 `story_task`、`visual_subject`、`must_show`、`must_not_show`、`visual_result`、`science_evidence` 和 `composition_reason`。`page_production.assemble_page_task` 将 storyboard 中的该字段传给宿主任务；缺少时回退到 manifest，旧页面保持兼容。它只验证文字约束进入任务，不把结构检查写成真实图像或人工审美通过。

页面清单可以声明 `continuity_invariants`：`character`、`recurring_props`、`scene_and_lighting`、`science_stages`、`reference_pages`。它们只约束高价值、可观察的跨页关系，不代替故事、研究证据或人工审核。结构错误、越界路径、缺失/哈希错误引用和科学阶段冲突是 block；科学可读性、道具漂移、光影和缺少可选参考页进入 warn。

规划完成后，在第一张正式图片提交前运行一次：

```bash
python3 "$SKILL_DIR/scripts/project_preflight.py" \
  /absolute/project b01 --version v1 --phase pre_generation --mode strict
```

预检是只读的，不创建队列、不写项目、不调用图片模型。`report-only` 只用于诊断。`generation_queue.py init` 在这些前置门禁**之前**不能运行；它不会替代 Research、教育目标、内容、strict-assets 或比例检查，只验证自己的结构输入。

strict 回执是后续轻量流程的复用凭证。至少保存：`status`、`phase`、`mode`、`blockers`、`warnings`、`write_operations`、`image_model_calls`、页数、`page_task_assembly.plan_fingerprint`，以及 Research/claim、批准资产/画风和引用文件的 SHA-256。现有回执没有统一顶层输入哈希时，使用这些已有证据组合判断；关键字段不能比较时，重新运行一次 strict，而不是猜测仍然有效。

关键输入没有变化且上述证据可逐项核对时复用回执；关键输入发生变化或无法证明一致时，只重新运行一次整本 strict。正常逐页生产不重复整本研究、全书规划、全量测试或开发探针。

## 2. 阶段 B：队列与逐页轻量路径

### 2.1 一次建立队列

一个 `single-coordinator` 运行一次：

```bash
python3 "$SKILL_DIR/scripts/generation_queue.py" init \
  /absolute/project/books/b01/v1 \
  /absolute/project/books/b01/v1/review/production-queue.json \
  --max-in-flight 1 --max-attempts 2
```

默认生产使用 `max_in_flight=1`，一次只领取和提交一个页面。现有队列实现仍允许把上限配置为 2—3，并提供 `claim-batch` 兼容入口；这些只是本地领取/记账能力，`max_in_flight` 不等于真实并行，也不是图片工具并发许可，默认流程不得使用它们开启并行。队列负责缓存、失败记录、断点续跑和 `reset-page`，不调用图像服务，也不自动生成多套备选。

### 2.2 继续已有项目：轻量检查后直接生图

逐页只执行以下检查：

1. 读取项目简要状态、目标页队列任务和当前页面提示词；不要重新读取无关历史审计。
2. 确认 strict 回执仍满足复用条件；比较当前全书计划指纹、当前页 `request_fingerprint`/`asset_dependency_fingerprint`、研究/claim 哈希、角色/画风版本和页面输出路径。
3. 确认当前页为 `pending`/可领取、没有未结束的同页请求、候选与正式页隔离。
4. 读取当前页的已解析资产和 `continuity_task.prompt_addendum`，确认科学阶段、固定道具、动作和文字安全区已进入实际任务。
5. 获取既有提示词和资产，不重写故事、分镜、全书提示词或已验收页。
6. 取得本次用户授权后，领取一页，记录 `current_request_id`、页码、`page_version`、`revision`、`attempt`，再调用现有图像工具一次。前一页取得明确成功、失败或合法终止结果前，不领取下一页；`pending_unknown`、超时或其他阻断立即停止批次。

正常生产不再逐页运行 Research、完整故事验证、全部页面审计、全量资产哈希、图片工具探针或全套测试。输入变化是例外：故事/研究、关键资产、连续性契约、页数或预检规则变化时，先使受影响证据失效并重新运行一次整本 strict；单页提示词或资产变化只重置该页、只重新生成该页。

### 2.4 知识主题入口

入口有两种等价起点：

1. 用户提供成人知识书籍或章节，按范围改编；
2. 用户只提供科学、数学、经济学等知识主题，先使用现有 `kids-knowledge-research` 研究包和事实追溯，再完成原创绘本。

第二种入口不要求用户提供一本书；当前已验证的 `kids-knowledge-research` 上游只支持 `age_band: 3-4`。因此，5—7 或 8—10 岁只给主题时，必须先提供成人知识来源或已审研究包；不得把 3—4 岁研究结果静默当作其他年龄段的研究依据。研究 Skill 仍只负责可靠知识发现、核验和研究包，不把创作职责迁移给研究 Skill。

### 2.3 请求生命周期

```text
claim
→ 保存 request_id、page_version、revision、attempt
→ 执行一次真实图片调用
→ 观察到提交动作后 mark-submitted
→ 接收工具返回
→ 保存独立候选并校验格式、路径、尺寸和 SHA-256
→ complete，随后等待人工视觉审核
```

`mark-submitted` 只表示宿主观察到提交动作，不证明服务端已接受；没有服务端任务编号写 `backend_task_id=unknown`。`complete` 需要 `submission_observed=true`。

本地包装器无返回时严格执行：

```text
timeout-request
→ 检查本地产物
→ 没有有效返回时 pending-unknown
→ 停止，不重试、不领取下一页
```

恢复必须有新的明确用户授权，再按 `authorize-recovery → claim-recovery → 新 request_id/revision → 一次调用` 执行；候选路径不得覆盖正式页。不得把调用开始当作提交成功，不得把 pending_unknown 改写成失败或成功。

## 3. 阶段 C：页面审核与整本交付

单页返回后做与风险匹配的页面检查：文件和尺寸、角色/画风、科学证据、文字安全区、道具和相邻页连续性。视觉判断保留人工/模型 `layout_review`、`text-image state matching` 和 `adjacent-page pair`；一次页面生成不等于批准。

明确要求可阅读图文成品时，排版使用字体实际**字形宽度**计算中文换行和正文高度；标点不能错误地出现在**标点行首**或独立成行。每页可提供 `text_safe_area_candidates`，但候选筛选只依据已声明安全区的几何关系，不声称自动识别人脸、表情或科学对象。字号只能有限调整，无法安全容纳时记录排版阻断，不删除或改写正文。3—4岁文字密度检查只报告拥挤、长对话和阅读停顿问题，不自动修改故事。

必须分别记录：图片工具是否返回成功、技术规格是否通过、人工视觉审核是否通过、最终发布是否批准。严格预检和技术规格门禁不能代替人工视觉审核；未获最终批准的项目不得标记为正式发布完成。

全部授权页面完成后再统一：

1. 使用 `build_pure_image_delivery.py` 生成一版完整成品；明确请求社媒成品时才使用 `render_social_book.py`。
2. 检查逐页正文、无字源图、最终交付图 `1080×1440` RGB 3:4、源/派生哈希、图文融合和 `contact_sheet_review`（缩略图总览）。比例正确但为 `1086×1448` 的原图只能作为可追溯源图，不能直接当作原生最终页。
3. 运行同一规则集的 `pre_delivery` strict 预检；这次才要求正式图齐全、页序正确、候选与正式页分离及人工审核记录。
4. 需要归档时按当前业务书号和输入哈希调用现有 `incremental_archive.py`，禁止按项目根目录第一个交付文件猜测书籍。

当前新成品默认是一版完整成品；不默认生成 PDF、打印拼版、9:16 或第二套候选。旧打印分支仍可在明确请求时使用 `export_book.py`、`validate_exports.py` 和 `acceptance`。

## 4. 证据与指标

四类证据互不替代：`engineering evidence`、`content evidence`、`visual evidence`、`real-reading evidence`。脚本提供 deterministic gates，`never automatic proof`；没有人工或真实共读证据时保持 `pending`。

每册指标保持现有字段：

```json
{
  "wall_clock_ms": "unknown",
  "image_artifact_span_ms": "unknown",
  "model_wait_ms": "unknown",
  "image_generation_calls": "unknown",
  "attempts": "unknown",
  "failures": "unknown",
  "retries": "unknown",
  "rework_rounds": "unknown",
  "cache_hits": "unknown",
  "resume_events": "unknown",
  "output_quality": "pending"
}
```

报告比较总耗时、总墙钟、绘图产物跨度/模型等待、调用数、失败率、返工、缓存、断点恢复和输出质量；失败率必须写清分母。没有同环境可复测基线时写 `baseline_unknown`。

## 5. 跨书与历史兼容

归档和交付先按当前 `version`、页数、页序、业务书号、`content_root`、`input_hashes` 和逐页源哈希验证目标书；不能因另一册存在 `status=passed` 就复用。旧 schema-v1 只有在书籍路径和逐页哈希明确一致时兼容。资产、页面和队列失败保留明确 `failure_code`，不写成 `completed`。

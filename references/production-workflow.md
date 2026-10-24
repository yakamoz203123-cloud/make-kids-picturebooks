# 精简生产流程 V1.2（第一阶段）

本流程仍由 `make-kids-picturebooks` 一个 Skill 执行。第一阶段只精简默认路径和文档责任，不新建缓存数据库、状态机、队列或审批服务，不改变 `schema_version: 1`。

## 第一阶段最短路径

```text
新项目：输入契约 → 知识门禁 → 故事/整本分镜 → 资产锁定
      → 一次整本 strict 预检 → 串行逐页生图 → 页面审核
      → 失败页局部返工 → pure-images 确定性交付 → 最终验收

续做项目：项目摘要 → 当前页任务/依赖 → 有效预检回执复用检查
      → 当前页轻量检查 → 串行生图 → 页面审核
```

默认不进入 PDF、打印、社媒渲染、历史迁移、发布打包或完整性能统计；这些是按需分支或历史兼容分支。

## 0. 输入契约和唯一职责

开始前只确认来源、目标年龄、输出模式、隐私范围、已批准角色/画风和本次授权。已有项目先读取摘要，不默认重新扫描整个项目。

| 对象 | 唯一职责 |
|---|---|
| 项目契约 | 来源、年龄、输出模式、隐私和授权 |
| knowledge whitelist | 允许使用的事实 |
| 故事/分镜产物 | 教育目标、故事、视觉事件和页面任务 |
| asset registry | 角色、画风、参考图和版本 |
| page manifest | 当前页面的生产约束 |
| generation queue | 领取、提交、候选、失败和恢复 |
| delivery manifest | 源图、派生图、哈希和交付关系 |
| review/acceptance | 内容、视觉、阅读和发布结论 |

不要让两个文件同时成为同一信息的权威来源。引用可以重复，定义只能有一个负责人。

### 项目包类型和依赖闭包

`project.json.project_profile` 必须区分项目用途：

- `production-ready`：可做 strict 预检、串行逐页生图、单页返工和确定性交付。每个页面声明的 `current_prompt_path`/`prompt_path`、`character_reference_path`、`production_reference_path` 都必须存在并位于当前书籍目录内；研究包、knowledge whitelist 和 story-claim trace 也必须能从项目契约解析。
- `delivery-only`：只用于已有图片的纯图交付和哈希校验，不承诺可续做，不得初始化生产队列。

没有显式 profile 的历史项目会由预检根据依赖完整性推断，并在回执中标记 `legacy-undeclared` 或 `production-ready`。新项目不要省略 profile。

`project_preflight.py` 的 `production_dependency_closure` 是只读门禁：它不复制文件、不创建队列、不调用图片模型，只报告 `missing`、`outside_book`、`warnings` 和实际解析证据。缺少生产依赖时，先修复项目包或明确降级为 `delivery-only`，不能靠跳过 strict 继续生图。

## 1. 新项目：一次完成规划

这是一次规划，不在逐页生产阶段重复整本研究、故事编辑或全书审计。

先完成知识门禁、教育目标卡、角色身份锁定、完整 `story.md`、全书 `storyboard.json`、逐页正文、`page-manifest.json`、`layout.json` 和页面任务。

故事顺序是“先故事、再页面、再镜头”：采用视觉事件驱动分页，允许删除、合并、拆分或调整页面，由故事和视觉事件自主决定页数。正文中的多个重要动作或知识事件必须删减、拆分或重新安排，直到一张静态图能表达本页主要事件；每个关键科学变化通过儿童行动—期待—发现推动，不只列成观察说明清单。

分镜完成后先做整本视觉节奏，再逐页选镜头；每页一个主要视觉任务，写清故事任务、视觉主角、关键动作、科学证据、构图理由、文字安全区和前后页状态；最后做相邻页重复审计，只保留有价值的重复。

Research 输入包先运行 `content_gate.py validate-packet`，生成 `knowledge-whitelist.json`；故事完成后运行 `content_gate.py validate-story`，页面完成后运行 `content_gate.py validate-manifest`。`page-manifest.json` 是页面科学证据的唯一事实来源，`storyboard.json` 不复制同一组页面字段。教育目标卡的字段要求见 [education-goals.md](education-goals.md)。

## 2. 一次整本 strict 预检

规划、资产解析和 `layout_design` 完成后，在第一张正式图片提交前运行：

```bash
python3 "$SKILL_DIR/scripts/project_preflight.py" \
  /absolute/project b01 --version v1 --phase pre_generation --mode strict
```

预检只读，不创建队列、不写项目、不调用图片模型。`report-only` 只用于诊断。`generation_queue.py init` 在这些前置门禁之前不能运行；它不会替代 Research、教育目标、内容、strict-assets 或比例检查，只验证结构输入。正式 `xiaohongshu-feed-3x4` 页面源图的期望画布是精确 `1080×1440`、RGB、无 alpha；队列缓存检查和 `pre_delivery` 正式图片检查必须使用同一契约，不能只因为图片比例为 3:4 就复用其他尺寸。

strict 回执至少保留 `status`、`phase`、`mode`、`blockers`、`warnings`、`write_operations`、`image_model_calls`、页数、`page_task_assembly.plan_fingerprint`、内容闸门 evidence，以及研究/claim、批准资产/画风、引用文件的 SHA-256。

正式交付的页面审核问题较多时，可以生成一个只读汇总清单：

```bash
python3 "$SKILL_DIR/scripts/review_checklist.py" \
  /absolute/project b01 --version v1 \
  --output-dir /absolute/reports/review-checklist-v1
```

它复用 `project_preflight.py --phase pre_delivery --mode report-only` 的结果，把页面问题按页聚合，把图片规格、人工审核和样式审批列为全局问题，并同时生成 `review-checklist.json` 与 `review-checklist.md`。这是人工工作台，不是新的生产阶段；它不会自动把 `pending` 改为 `passed`，也不会覆盖已有输出。

## 3. 串行逐页生产

一个 `single-coordinator`（单一协调器）初始化一次队列：

```bash
python3 "$SKILL_DIR/scripts/generation_queue.py" init \
  /absolute/project/books/b01/v1 \
  /absolute/project/books/b01/v1/review/production-queue.json \
  --max-in-flight 1 --max-attempts 2
```

默认 `max_in_flight=1`。队列仍保留 2—3 的兼容配置和 `claim-batch` 入口，但它们只是本地领取/记账能力，不是图片模型并发许可。队列只负责缓存、失败记录、断点续跑和 `reset-page`，不调用图像服务，不自动生成多套备选。

每页执行：

```text
检查当前页任务和依赖
→ 检查已有结果，避免重复提交
→ 用户授权后 claim
→ 保存 request_id、page_version、revision、attempt
→ 一次真实图片调用
→ 观察提交动作后 mark-submitted
→ 保存候选并校验路径、尺寸和 SHA-256
→ 页面审核 pending/通过/失败
```

队列的 `cached` 只表示当前正式画布、比例、可解码性和请求 fingerprint 均满足缓存条件，不表示人工视觉审核已经通过；最终仍需 `review.json` 和逐页视觉证据。

先完成 `layout_design` 再调用图像生成器；稳定基础提示词只保留画风、角色不变特征、比例、全局禁项和文字安全区，每页只追加场景动作、道具、知识证据及前后页状态。正式参考图使用 `production_reference_path`。每页一次生成；历史“两页一批”不代表并行许可。

超时按 `timeout-request → 检查产物 → pending-unknown → 停止` 处理。未经新授权不得恢复、自动重试或领取下一页；不要把调用开始当作提交成功，也不要把技术生成成功当作人工视觉批准。

## 4. 续做最小读取集

已有项目续做时，只读取：

1. 项目摘要；
2. 当前页任务；
3. 当前页依赖资产和 `continuity_task.prompt_addendum`；
4. 有效预检回执；
5. 当前页队列状态；
6. 当前页输出路径和授权状态。

不要重复 Research、完整故事验证、全部页面审计、整本测试、全量资产哈希或图片工具探针。前一页取得明确结果前，不领取下一页。

## 5. 失效和重新规划

研究内容、年龄档、故事、页数、关键角色/画风、连续性契约、输出模式或预检规则变化，或者无法证明关键依赖未变时，重新运行一次整本 strict。

单页提示词或单页资产变化只使当前页失效，只重建和重新生成该页；不要把单页返工扩大成整本重做。

## 6. 页面审核和确定性交付

页面返回后检查文件、尺寸、角色/画风、科学证据、文字安全区、道具和相邻页连续性，并记录 `layout_review`、`text-image state matching` 和 `adjacent-page pair`。

全部授权页面完成后，默认使用 `build_pure_image_delivery.py` 生成一版完整成品；保留无字源图、独立正文、源/派生哈希、缩略图和交付清单。四类证据分别记录：`engineering evidence`、`content evidence`、`visual evidence`、`real-reading evidence`。没有人工视觉审核或真实共读证据时保持 `pending`。

## 7. 按需分支和历史兼容分支

- 可阅读图文成品：读取 `composition.md`、`social-output.md`，使用 `render_social_book.py`、`render_social.py` 和 `accept_social_book.py`。
- PDF/打印：读取 `printing.md`、`acceptance.md`，使用 `export_book.py`、`validate_exports.py`、`acceptance` 和 `impose_booklet.py`。
- 历史社媒迁移、归档、发布打包和完整性能诊断：只在明确请求或诊断需要时启用。

这些分支不得改变默认 `pure-images` 输出，也不得把旧版成功记录当作当前项目自动批准。

## 8. 指标

只记录真实可观测的总耗时、图像产物跨度、真实模型等待、图像生成调用次数、失败率、返工、缓存命中、断点恢复和输出质量；不可观测值写 `unknown`，不能由空错误列表推断为零。

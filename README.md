# make-kids-picturebooks

宝宝知识绘本技能：把成人知识书或已核验的知识主题改编为适龄原创绘本生产工作包。

当前发布版本：`v0.11.0-preview`。

默认交付是 `pure-images`：逐页无字插画、独立可编辑正文和可追溯的审核记录。可阅读图文、PDF、打印拼版、社媒版式和 9:16 输出均需用户明确请求。

## 默认最短流程

```text
输入契约 → 知识门禁 → 故事/整本分镜 → 资产锁定
→ 一次整本 strict 预检 → 串行逐页生图
→ 页面审核 → 失败页局部返工 → pure-images 确定性交付
```

继续已有项目时只读取项目摘要、当前页任务/依赖、有效预检回执和当前页队列状态。研究、年龄档、故事、页数、关键角色/画风、连续性契约、输出模式或预检规则变化时才重新运行整本 strict；单页提示词或资产变化只返工当前页。

PDF、打印、社媒渲染、历史迁移、发布打包和完整性能统计属于按需或历史兼容分支，不会因脚本存在而自动进入默认流程。

## 日常统一入口

默认操作可以压缩为三个动作：

```text
python scripts/workflow.py doctor /absolute/project b01 --version v1
python scripts/workflow.py resume /absolute/project b01 --version v1
python scripts/workflow.py resume /absolute/project b01 --version v1 --approval "用户批准继续生成下一页" --max-calls 1
python scripts/workflow.py deliver /absolute/project b01 /absolute/project/books/b01/v1/delivery/pure-image-delivery-v1 --version v1
```

`doctor` 是只读项目检查；`resume` 复用预检和队列，默认单页串行，没有授权只提示、不领取，运行中的页面会等待；`deliver` 委托最终交付门禁。底层脚本仍保留，用于详细诊断、生命周期处理和历史兼容，不会被统一入口绕过。

## 项目包类型

`project.json` 使用 `project_profile` 明确项目包用途：

- `production-ready`：包含故事、分镜、页面清单、prompt、角色/画风批准引用、研究追溯和页面依赖，可运行 strict 预检、串行队列和逐页返工。
- `delivery-only`：只保证已有图片、正文、顺序和交付哈希，可用于 `pure-images` 交付，不得当作可续做的生产项目。

默认新项目使用 `production-ready`。`project_preflight.py --phase pre_generation --mode strict` 会检查页面依赖闭包；缺少 prompt、角色参考或生产参考时会明确阻断，不再只依赖页面清单存在。显式未知的 `project_profile` 也会阻断，不会被推断成 `production-ready`。

资产版本以 `assets/style-registry.json` 为准：默认 `STYLE-CORE-01:v1.2` 绑定 `core-characters-v1.2`；已发布的 `STYLE-06:v0.1` 可在页面明确选择时使用 `core-characters-v1.3`，但不会改变全局默认。

正式项目创建队列前必须存在 `project.json` 并通过 strict preflight；无项目契约的低层历史队列只有在明确传入 `--standalone-legacy` 时才允许创建。直接调用 Python API 的旧测试兼容参数暂时保留，生产 CLI 不默认绕过项目门禁。

正式项目的 `generation_queue.py init` 会自动复验 strict 门禁，并在队列中保存绑定当前项目、版本和计划指纹的 `preflight_receipt`；门禁未通过时不会创建队列。队列建立后，普通 `claim` 还需要先用 `authorize-generation` 记录一次有限次数的用户授权。

当 `page-manifest.json` 声明了 Research 白名单和 story trace 时，strict 预检会同时运行故事追溯与页面科学视觉闸门。页面级 `knowledge_claims`、`science_visual_checks` 和全书级 `science_visual_consistency` 只维护在 page manifest；`storyboard.json` 不重复保存同一份页面证据。

正式 `xiaohongshu-feed-3x4` 页面源图必须实际为 `1080×1440`、RGB、无 alpha；队列缓存和正式交付预检使用同一精确画布契约。比例为 3:4 但尺寸为 `1086×1448` 的历史图片不会被当作正式缓存。`content_gate.py` 的中文 CLI 输出会按 UTF-8 配置，避免 Windows 默认代码页造成误报。

正式交付需要集中人工处理多个页面问题时，可生成只读审核清单：

```text
python scripts/review_checklist.py /absolute/project b01 --version v1 --output-dir /absolute/reports/review-checklist-v1
```

该工具只汇总 `pre_delivery` 的现有结果，输出 JSON 和 Markdown；它不会修改 `pending` 状态、创建队列、调用图片模型或代替人工批准。输出目录必须是新的，工具不会覆盖已有清单。机器状态为 `blocked` 时命令返回退出码 `2`，便于自动流程停止。

`build_pure_image_delivery.py` 只构建技术交付包，`delivery-validation.json` 会保留 `release_status: human_review_pending`。完成项目审核后，使用 `scripts/release_pure_image_delivery.py` 通过 `pre_delivery/strict` 并写入唯一的 `release-receipt.json`；没有人工最终批准不会进入 `released`。

## 本地验证

```text
python -X utf8 -m compileall scripts
python -X utf8 -m unittest discover -s tests -q
python -X utf8 -m pip check
python scripts/package_skill.py . ../dist/make-kids-picturebooks-v0.11.0-preview.zip --version 0.11.0-preview
```

CI 运行指导、发布门禁和技能打包的聚焦测试；完整测试集包含渲染和外部环境相关用例，需在具备对应工具的环境中单独运行。

仓库不包含用户书籍、儿童资料、私人角色照片或生成项目。发布包名为 `make-kids-picturebooks-v0.11.0-preview.zip`。

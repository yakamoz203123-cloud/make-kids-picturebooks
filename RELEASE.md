# make kids picturebooks 0.11.0-preview

## 发布范围

这是保留 `schema_version: 1` 兼容性的质量与效率验证预览版本，发布包名为 `make-kids-picturebooks-v0.11.0-preview.zip`，包含以下改进：

- Windows 和 Linux 下的项目相对路径规范化；
- 来源文件和角色目录的显式资产边界；
- 字体文件、许可证和来源证明的验收要求；
- 故事页正文顺序核对，封面和封底不误判为朗读稿；
- UTF-8 测试夹具和当前 PyMuPDF 导入方式；
- 来源内容安全边界、年龄选择、角色确认和画风确认规则；
- 单顶层目录技能包与完整下载包的非覆盖式打包；
- 保留三种历史版式兼容：`scene-integrated`、`soft-card`、`narrative-band`；当前新生产只允许 `scene-integrated`。
- 版式设计契约、逐页 `layout_review` 审核记录和版式/清单/验收一致性检查；
- 默认新输出是 `pure-images`：原生 `1080×1440`、源图3:4、无字插画、独立正文和确定性交付清单；小红书静态图文、阅读 PDF、家庭打印拼版、抖音/9:16或多套候选均为明确请求时的可选/历史分支。
- 小红书新页面要求 `portrait-full-bleed` 竖版满幅构图与 `in-scene` 画面内文字；模板和确定性门禁拒绝底部通栏文字区。
- 正式社媒插画前增加生成器比例预检：`preflight_image_generation.py` 读取实际探针尺寸，比例不符返回 `image_generation_blocked`，禁止横图适配后继续排版。
- 增加真实儿童原型的私有角色 Bible 规则：`privacy_scope` 与 `public_release` 分离，角色参考必须保留版本，公开 Skill／GitHub 包不包含照片、角色图或个人资料。
- 增加快速出图协议：展示型角色页与干净生产参考图分离，先完成 `layout_design`，按每页一次、串行推进，先检查已有结果后再决定是否处理失败，避免重复提交长任务。
- 增加单 Skill 分阶段生产队列：正式出图前完成全书故事与分镜，使用 `scripts/generation_queue.py` 记录一页一个任务、默认按单页串行推进；队列仍保留 2—3 的本地领取上限作为兼容配置，但不代表图片模型并发许可，也不自动生成多套备选。
- 默认交付改为 `pure-images`：新增 `build_pure_image_delivery.py`，一次性构建无字图片、独立正文、图文清单、哈希、缩略图与确定性校验；PowerPoint、字幕合成和社媒成品改为显式调用的兼容能力。
- 新增 `production_timing.py` 阶段计时记录器，并将阶段汇总接入 `production_metrics.py`；未完成或不可观测的阶段保持 `unknown`，不把并发累计时间冒充墙钟时间。
- 增加优化前后性能报告规范：区分可观测总墙钟、图像产物跨度、真实模型耗时、失败率、返工和缓存命中，不用验收空错误推断旧流程失败率为零。
- 增加教育目标卡：在正式分镜前完成 `core_knowledge`、`target_age_band`、`prior_experience`、`visible_relationship`、`knowledge_boundary` 和 `reading_observation`。
- 保留可选社媒成品渲染与验收：用户明确选择时，`render_social_book.py` 生成小红书3:4逐页成品，`accept_social_book.py` 检查画布、源图比例、逐页图像可读性与审核证据；`migrate_social_only_layout.py` 仍只用于旧项目的非覆盖式版面迁移。
- 增加四类分离证据：engineering evidence、content evidence、visual evidence 和 real-reading evidence；整书必须记录实际 `contact_sheet_review`，不能把确定性检查或缩略图总览写成自动审美或儿童理解证明。
- 明确队列是 `single-coordinator`（单一协调器）；`max_in_flight` 只是宿主领取上限，不等于真实并行。生产记录统一保存 `metrics` 字段，缺少真实观测的指标标为 `unknown`。
- 增加 Research 四文件输入门禁、`allowed_knowledge` 白名单、逐句 story-claim trace 和 storyboard science visual checks；未验证科学断言、禁止状态或错误 claim 绑定会阻断内容生产。
- 增加 core-v1.2 资产绑定契约：固定 `CHAR-GIRL-01`／`CHAR-BOY-01`／`CHAR-MOTHER-01` 别名、`asset-bound-page-v1` 页面规格、`page-production-registry.json`、`style_master.json` 与 `manifest-receipt.json`；`core-v1.2` 仍是当前默认解析入口，`core-v1.3` 只作为显式/阶段性资产，不在本版本自动切换；不改变角色视觉设计。
- 增加可选 strict-assets 清单门禁：新页面可用 `--strict-assets` 验证批准版本、参考图、资产兼容性和哈希；旧 `schema_version: 1` 页面仍可按原规则读取。
- 增加页面级机器可读失败码和资产依赖指纹说明；缓存、重试、断点恢复和单页返工的行为仍由现有 `generation_queue.py` 负责。

## 质量门迭代

本次 0.11.0-preview 质量门迭代在不改变 `schema_version: 1` 的前提下增加；PDF／打印条目只描述历史兼容分支：

- 朗读版和印刷版 PDF 的非空、可读、页数、尺寸、可提取正文与最终字号确定性校验；印刷版默认最小字号为 18 pt，项目只能提高该阈值；
- 页间连续性记录：`previous_page_state`、`current_page_entry`、`next_page_hook`，以及有实际证据的 `text_image_match` 和 `continuity_review` 通过记录；
- 数字完成时对连续性记录、相邻页状态衔接和人工/模型视觉审核证据的强制检查；
- 稳定角色参考、文本与画面状态匹配、相邻页成对审核和最终输出检查的操作指引。
- 图像与文字分层、文字安全区锁定、版式模式一致性和社媒安全区检查。

这些检查只报告确定性缺陷；角色一致性、场景可读性和故事/科学准确性仍须由人工或模型进行视觉审核。`soft-card`、`narrative-band`、9:16与打印脚本仅为旧项目复核保留。

## 兼容性

- Python 3.10 及以上；
- 目标验证平台为 Windows 和 Linux；
- 依赖版本见 `requirements.txt`；
- 历史打印分支默认质量为 300 DPI 或更高，使用项目内附带的中文打印字体；当前默认无字成品以原生 `1080×1440` 和3:4源图为准，可阅读小红书成品另按明确请求验收。

## 验证命令

```text
python -X utf8 -m compileall scripts
python -X utf8 -m unittest discover -s tests -q
python -X utf8 -m pip check
```

发布前还应在 Windows 和 Linux 上分别运行上述命令，并检查验收、续做、打包和重复执行不会覆盖已有输出。

## 已知范围

本版本不包含音频、视频、搜索 Skill、新的付费图像接口、真实并行图像调用承诺、Schema v2、多年龄独立队列和 3–4、5–7、8–10 岁三套真实样册。默认只输出一套 `pure-images` 无字源图与独立正文；小红书图文、PDF、家庭打印拼版、9:16或多套候选只有在用户明确提出独立需求时才走可选/历史分支。仓库中的版式样例只用于渲染回归和人工查看，不代表自动审美通过。Grok Bot 的具体 API 接入仍不包含；本版本只提供平台无关的3:4实际输出比例预检，不会让不支持竖版的生成器获得竖版能力。行为评测更新结果、真实儿童阅读反馈和完整三年龄样册仍不是本预览版已经完成的证据，属于后续发布门槛。

公开包只包含技能源码、测试、脚本、参考资料、模板、许可证和字体来源证明，不包含任何用户书籍、儿童资料、角色参考或生成项目。

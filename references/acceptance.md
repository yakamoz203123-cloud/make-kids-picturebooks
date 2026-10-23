# 验收与导出

## 制作记录

当前默认交付 `pure-images`：逐页无字源图、独立可编辑正文、交付清单/缩略图和审核记录。明确请求时仍可输出一套小红书3:4静态图文；阅读 PDF、家庭打印拼版、9:16 和旧 ZIP 也都是可选/历史分支，不属于默认输出。

默认新册的 artifacts（成果路径）保存 concept、education_goal、story、storyboard、layout、page_manifest、pure_image_delivery、review；明确请求可阅读图文时再保存 social_output，历史打印册才额外保存 reading_pdf、print_pdf。所有资产放入项目目录，路径相对于其记录文件；不依赖旧工作区、账号或机器字体目录。保存角色参考目录 characters_path。字体许可与嵌入字段只在社媒阅读或打印分支需要时加入，不把字体复制要求当作无字源图默认门槛；若该分支复制字体，仍须保留 `font-license.txt` 和 `font-provenance.json`。

`review.json` 必须把证据分成四个域：`engineering_evidence`、`content_evidence`、`visual_evidence` 和 `real_reading_evidence`。工程证据只证明可重复的文件与脚本检查；内容证据核对来源、教育目标卡、年龄和故事；视觉证据核对逐页与整书成页；真实阅读证据只来自实际共读、试打或用户反馈。缺少真实阅读时记录 `status: "pending"`，不能用数字检查或目标卡代替。

同一记录保存 `contact_sheet_review` 和 `metrics`。`contact_sheet_review` 至少包含 `status`、`evidence`、`image_path`、`reviewer`、`reviewed_at`，实际查看整书缩略图总览后再填写；它不能替代逐页 `layout_review` 或自动证明审美。`metrics` 至少包含 `wall_clock_ms`、`image_artifact_span_ms`、`model_wait_ms`、`image_generation_calls`、`attempts`、`failures`、`retries`、`rework_rounds`、`cache_hits`、`resume_events` 和 `output_quality`；没有观测到的值写 `unknown`，不填推断的零。

版面每页填写 kind（页面类型）：cover（封面）、story（故事）、parents（家长说明）、back（封底）或blank（有意留白）。需要无字的 story 页还必须显式设置 `wordless: true`；空正文的其他页面必须使用 `kind: "blank"`，不能仅依靠空字符串。故事页必须有实际插画、background（背景）图像角色和已实际查看的文字留白确认。清单选图、版面选图及文字区域必须一致，正文与分镜逐字一致。逐页清单的知识检查应记录实际观察，不把生成提示当证据。

## 质量选择

默认无字交付不使用打印 `quality_profile` 作为成品门槛：源图使用原生 `1080×1440`、3:4 基础画布，并按逐页内容/科学/连续性和人工视觉审核验收。`quality_profile`、`target_dpi`、`quality_approval` 以及社媒文字几何只在用户明确要求打印或可阅读图文分支时启用。

## 导出和审核

默认顺序是：运行 `build_pure_image_delivery.py` 生成无字源图的确定性交付副本、独立正文、清单和缩略图；随后实际查看每页与整书缩略图，保存 `pure_image_pages`（或 `delivery_pages`）、`contact_sheet_review` 和四类 evidence。明确要求可阅读图文时，才运行 `render_social_book.py`、保存 `social_pages`/`layout_review` 并运行 `accept_social_book.py`；明确要求打印时才运行 `export_book.py`、`validate_exports.py` 和 `accept_book.py`。旧版社媒分支的记录仍可写作“当前新册最终顺序是：运行 `render_social_book.py` 到新的版本目录”，但这不是默认路径。实际检查每一页人物、数量、动作、知识条件、留白和连续性，不仅检查文件存在或抽样页。

默认 `review.json` 保存 `pure_image_pages` 数组，每项对应连续页码；明确要求可阅读图文时另保存 `social_pages`，历史打印版本才保存 `reading_pages` 和 `print_sides` 数组。默认记录示例为：

```json
{"pure_image_pages":[{"page":1,"status":"passed","source_path":"output/v1/source/page-01.png","delivery_path":"output/v1/pure-images/page-01.png","visual_review":{"status":"pending","evidence":"等待人工查看人物、科学现象和连续性。"}}],"unresolved_digital_defects":[]}
```

上述仅展示默认无字交付结构，实际记录须覆盖全部页，并另保存四类 evidence、`contact_sheet_review` 和 `metrics`。可阅读图文或打印分支的页面数组另存于对应版本。家长说明没有插画时，清单 current_image_path 指向实际审核的渲染页，不能填空白替代文件。记录图像生成调用次数、修订次数及未解决问题；实物打印和共读反馈独立记录，未发生时明确待验证。

## 完成及续做

默认用无字交付清单、页面技术检查和人工/模型视觉审核重新检查最终素材；所有工程、内容和视觉检查通过后才设为 digital_checked（数字检查通过），并保存 acceptance 记录。明确要求可阅读图文时再增加社媒布局与文字审核，明确要求打印时继续使用 `accept_book.py`。真实阅读证据在未发生时保持 `pending`，不能因此声称孩子已经理解。修改任一资产后重新生成受影响页面并重新审核，用新版本验收，不修改旧摘要来绕过检查。脚本是 deterministic gates，只核对可检查的结构和文件，never automatic proof；visual identity、scene readability、science/story consistency 仍由 human/model visual review 负责。

运行 project_state.py 时检查验收摘要，文件缺失或变更返回revalidate（重新验收）。在selected_topics（适龄主题模式）下只推进本次已选册队列，队列结束不自动续做未读章节或未选候选项。新项目默认此模式；旧项目缺少模式时脚本保留旧行为，执行者先按本次用户要求保存模式和主题队列，保留旧作品。用户点名修改旧册时先将该册加入本次队列。按章模式须有明确范围依据。

## 版式与社媒验收门禁

使用新版式时，`page-manifest.json` 与 `layout.json` 的每页 `layout_design`、`text_box_mm` 和正文必须一致。默认无字交付仍须记录自然文字安全区和视觉焦点，但不渲染文字；明确要求可阅读图文时才要求 `scene-integrated`、最大行数和平台避让区。`soft-card` 和 `narrative-band` 仅供历史项目复核。图像提示词必须要求完整单页且图像不得生成文字或伪文字，正文后置到可编辑文字层。

`layout_review` 是独立的逐页人工/模型视觉审核记录，至少说明文字和画面的关系、对比、遮挡、阅读顺序与页间连续性。字段存在、脚本通过、字体嵌入或 PDF 可提取，不能声称自动审美通过；`layout_review` 缺失、证据为空或未通过时，不得进入 `digital_checked`。验收脚本只能验证结构、文件和几何条件，视觉融合、人物身份、场景可读性和 science/story consistency 仍需 human/model visual review。

资产绑定验收还要核对 `production_schema: asset-bound-page-v1`、固定公共角色别名、core-v1.2 manifest、`manifest-receipt.json`、`page-production-registry.json`、`style_master.json` 和解析哈希。可以先用旧 `schema_version: 1` 规划；只有显式传入 `--strict-assets` 时才执行这组绑定门禁，避免把历史页误当成缺失资产而阻断续做。

正式逐页插画前，必须对实际图像生成器做一次 profile 探针预检：运行 `scripts/preflight_image_generation.py` 并保存 JSON 结果。它读取生成文件的实际尺寸；提示词或参数声明不算能力证据。若结果为 `image_generation_blocked`，不得继续正式插画或完成声明，不能把 `1280×720` 等横图缩放、中心裁切或补白成默认源图；可阅读图文分支还必须满足其自身社媒比例。

默认新册必须声明源图画布 `1080×1440`、比例 `3:4`、主体安全区和自然文字安全区；明确要求可阅读图文时，才增加 `social_layout.profile: "xiaohongshu-feed-3x4"`、画面内文字安全区、平台界面避让区与 `social_pages.layout_review`。检查逐页源图是否实际存在、尺寸是否正确、关键对象是否安全、源图是否原生符合3:4；不能用历史打印版替代实际审核。历史旧册可保留其9:16记录，但默认流程不创建或交付该 profile。

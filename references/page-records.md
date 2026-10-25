# 逐页记录与当前素材

复制 assets/page-manifest-template.json（清单模板），逐页记录所有成书页。页号从1按数组顺序连续。路径相对清单文件解析；当前采用图片和提示词明确选定，不扫描目录，不根据名称或修改时间挑新版。备份可保留，但不能混入成书。规划图片可为空；已有非空路径必须真实存在。

新生产页还应参考 `assets/page-production-template.json`，并填写 `production_schema: "asset-bound-page-v1"`。页面的 `character_asset_bundle`、`character_asset_version`、`characters`、`style_master_id`、`style_master_version`、`page_delta`、`source_prompt_hash` 和 `resolved_asset_hash` 共同描述图像依赖；角色可使用固定公共别名 `CHAR-GIRL-01`、`CHAR-BOY-01`、`CHAR-MOTHER-01`，解析结果仍必须回到批准的 core-v1.2 manifest。`assets/page-production-registry.json`、`assets/style_master.json` 与 `assets/characters/core-v1.2/manifest-receipt.json` 是页面绑定的约束来源，不把它们复制成第二份可变定义。

为让故事分镜真正进入生图任务，页面可增加 `visual_direction`：`story_task`、`visual_subject`、`must_show`、`must_not_show`、`visual_result`、`science_evidence`、`composition_reason`。它应来自 storyboard 的单页导演判断，manifest 可保存同一份兼容副本；任务组装优先读取 storyboard，缺少时回退 manifest。该字段是提示词输入证据，不是图片已经正确的证据。

页面还可以增加 `continuity_invariants`（schema version 1）。该字段是可选的，旧清单没有它时不补造数据。其内容只描述跨页连续性契约：固定角色与动作、重复道具的稳定形状/比例/材质、场景与光影方向、科学阶段顺序，以及项目内带 SHA-256 的前后页参考。声明了参考页就必须能在项目内解析，路径不能越界，实际哈希必须匹配；这些是确定性 block。视觉上是否真的保持一致仍由逐页、相邻页和整书人工/模型审核确认。

队列初始化后的 `page_task.continuity_task` 是该约束进入实际宿主任务的证据，包含结构化绑定、warn 提醒和 `prompt_addendum`。审核证据应保留 `current_page`、`constraints`、`references`、`structural_preflight`、`human_visual_questions`、`discovery_stage`、`rework_needed` 和 `human_final_conclusion`；不能把结构预检结果写成自动视觉批准。

清单 age_band（年龄档）必须填写已选的 "3-4"、"5-7" 或 "8-10"，与本册记录一致；模板空值用于提醒先选择，不能通过校验。旧册的 "5-6" 保留兼容，不自动扩大年龄范围。一份清单对应一册的一个年龄版本，不能填多个档位。

每页保存正文版本、角色版本、稳定的 `character_reference_path`（本页实际使用的已批准 character bible 路径）、以及正式生成时使用的项目相对 `production_reference_path`（与 Bible 同版本的干净生产参考图）、文字区域（与版面相同，左下角起算，毫米）、当前提示词路径、当前图像路径、道具及知识检查。道具编号同页唯一，数量为非负整数；记录位置、当前状态及相对前页的变化。泡泡等动态对象不要求每帧同数，但器具数量和影响知识的结构必须明确。旧项目若没有独立生产参考图，先补建并批准后再进入新的正式生成批次，不把展示型角色设定页默认为生产参考。

完成页必须填写 manifest continuity fields：`previous_page_state`、`current_page_entry` 和 `next_page_hook` 都是且仅是 `{"state_id":"稳定状态标识","summary":"可核对的本页状态说明"}`；相邻页中前页 `next_page_hook.state_id` 必须等于后页 `current_page_entry.state_id`。`text_image_match` 和 `continuity_review` 都是且仅是 `{"status":"pending|passed|failed","evidence":"实际观察的证据"}`。规划时可用 pending 与空证据；成书前必须为 passed 并填写实际证据，不添加其他字段，不改 schema_version。

页面失败保留机器可读 failure code，例如 `MISSING_ASSET`、`REFERENCE_NOT_FOUND`、`INVALID_DIMENSIONS`、`ASPECT_RATIO_MISMATCH` 和 `GENERATION_FAILED`；失败码不能替代人工审核结论。

知识检查为 pending（待检查）、passed（通过）或 failed（失败），证据填写实际看到的动作、对象与对应条件，可关联检查图片。封面及说明页写明不新增知识动作、文字条件审核结果。无插画说明页仍记录排版提示，完成时可将最终页面渲染图作为检查图；它不充当故事插画。

使用 Research 输入包时，每页另存 `knowledge_claims`（来自 `knowledge-whitelist.json` 的 claim ID）和 `science_visual_checks`。`knowledge_claims` 不得包含 `uncertain`、`pending_confirmation` 或 `omit`；推论必须保持推论身份。`science_visual_checks` 至少写清 claim、必须看到的结构/顺序/条件、状态和实际画面证据，不能只写“科学正确”。故事全文另存逐句 story-claim trace，并在进入正式分镜前通过 `content_gate.py validate-story`。

先校验规划，再用 --require-images（要求实际图片）校验完成记录。该模式要求所有选定图存在、检查通过且证据非空；它是 deterministic gate，只验证记录完整，不能自动判断知识、角色身份或图像准确性。

需要资产级门禁时，在旧校验之外显式增加 `--strict-assets`，并传入 core-v1.2 bundle 目录；不带该开关的旧 `schema_version: 1` 清单保持兼容。strict-assets 通过只说明页面绑定、版本、回执、参考图和哈希关系成立，不说明人物在实际图中一定一致或儿童一定理解。

成书前逐页核对：清单页号等于版面页号；正文版本对应保存稿；故事页清单当前图片等于版面实际图片（比较解析后的路径）；文字区域一致；无图说明页清单检查图对应最终渲染页。改图或改文字后相关知识和留白检查返回待检查，再生成新输出。

# make-kids-picturebooks 知识输入门禁补强审计

- 审计日期：2026-10-16
- Skill：`make-kids-picturebooks`
- 版本：`0.11.0-preview`
- 范围：小范围能力补强；不重做绘本架构、不修改 Research Skill、不接入新付费图像接口、不生成图片
- 真实输入来源：`E:\搜索skill\kids-knowledge-research\test_runs\cross-domain\`
- 审计输出：`E:\搜索skill\kids-knowledge-research\test_runs\knowledge-gate-audit-20261016\`

## 1. 结论摘要

本轮补强已经解决了 Research → 绘本内容生产之间最关键的确定性缺口：现在可以在写故事前验证 Research 四文件包，生成只允许使用的知识白名单；故事完成后，科学断言必须逐句绑定 claim；分镜还要记录每页的知识 claim 和视觉证据检查。

本轮不是完整绘本成品验收。由于任务明确要求不生成图片，三本真实回归均停在内容生产的 **B — knowledge passed**：输入、知识、故事、分页和科学追溯通过；角色一致性、画内排版、社媒成页、视觉审美和真实共读仍是 pending。因此不能声称达到 **C — production checked**。

## 2. 修改前后对照

| 能力 | 修改前 | 修改后 |
|---|---|---|
| Research 输入 | Skill 文档要求来源可追溯，但没有解析 `research_packet.md`、`sources.json`、`claims.json`、`child_concepts.json` 的正式门禁 | `scripts/content_gate.py validate-packet` 检查四文件存在、可读、JSON 解析、packet/age/topic 一致、claims/concepts 非空和引用闭合 |
| 知识使用范围 | 没有机器可读的“允许进入故事”的集合 | `build-whitelist` 生成 `knowledge-whitelist.json`，拆分 `allowed_knowledge`、`restricted_knowledge`、`blocked_knowledge` |
| 状态边界 | `fact`、`inference`、不确定信息主要依赖人工遵守文档 | `inference` 只能以推论使用；`uncertain`、`pending_confirmation`、`omit` 不能进入儿童事实；不满足适龄概念也不能进入白名单 |
| 故事科学断言 | 主要靠内容审核，缺少逐句反向追溯 | `validate-story` 要求科学句、科学观察和标记为科学的对白绑定 claim；缺失、禁止状态、推论升级和错误绑定都会阻断 |
| 页面知识 | 页面模板只有一般 `knowledge_check` | 新模板增加 `knowledge_claims`、`science_visual_checks`、Research/白名单/trace 路径字段 |
| 分镜科学一致性 | 有一般 storyboard 和视觉审核要求 | `validate-storyboard` 检查页面 claim、视觉证据、禁止状态和全书 `science_visual_consistency` |
| 真实跨主题证据 | 之前主要有冰融化内容审查 | 追加冰融化、种子发芽、为什么要洗手三个历史真实 Research 包的无图生产回归 |

## 3. 新增实现和文档

- `scripts/content_gate.py`
  - `validate_research_packet()`：四文件输入门禁。
  - `build_knowledge_whitelist()`：按事实状态、年龄适配和 child concept 生成白名单。
  - `validate_story_claims()`：逐句科学断言追溯。
  - `validate_storyboard_science()`：页面知识 claim 与视觉证据、整书科学一致性检查。
  - 支持 CLI：`validate-packet`、`build-whitelist`、`validate-story`、`validate-storyboard`。
- `references/research-input-gate.md`：输入合同、状态规则、trace 字段、页面字段和 A/B/C 成熟度边界。
- `SKILL.md`：把研究包门禁插入故事前流程；没有通过白名单和故事 trace 不进入正式分镜/插画。
- `references/page-records.md`、`references/review.md`：补充 `knowledge_claims`、`science_visual_checks` 和 storyboard-level 审核要求。
- `assets/page-manifest-template.json`、`assets/book-template.json`：增加 Research、白名单、story trace 和页面科学检查字段。
- `RELEASE.md`：记录本轮 Research 输入门禁能力。

没有修改 Research Skill、Research 四文件输入包或用户的私有儿童角色资料。此前已有的社媒版式/渲染改动被保留，没有用本轮补强覆盖或回滚。

## 4. 门禁逻辑

### 4.1 输入门禁

必须存在且可读取：

```text
research_packet.md
sources.json
claims.json
child_concepts.json
```

检查内容：

1. Markdown metadata 的 `packet_id`、`topic`、`age_band` 存在。
2. 三个 JSON 顶层 `packet_id` 和 `age_band` 与 Markdown 一致；JSON 若声明 `topic`，必须一致。
3. 所有 JSON 可解析、非空、无 NUL 损坏；sources、claims、concepts 都是非空数组。
4. source/claim/concept ID 唯一。
5. claim 的 source 引用、evidence location、source 的 supported claim、concept 的 linked claim 全部可回溯。
6. claim 的 `status`、`age_fit` 和 concept 的 `suitability.outcome` 必须在受支持枚举中。

任一项失败即 `blocked`，不搜索、不猜测、不写故事、不画正式插画。

### 4.2 知识白名单

- `fact + include + include concept` → `child_fact`。
- `fact + borderline` 在明确的 include/borderline 适龄规则下 → `child_fact` 或 `adult_mediated`。
- `inference` → 只进入 `restricted_knowledge`，必须保持推论语气。
- `uncertain`、`pending_confirmation`、`omit` → `blocked_knowledge`。

### 4.3 故事和分镜追溯

科学断言、科学观察和科学对白没有 `claim_ids` 时返回 `unverified_scientific_claim`。绑定 `uncertain`、`pending_confirmation`、`omit` 返回 `forbidden_claim_status`；将 `inference` 作为事实使用返回 `inference_promoted_to_fact`；提供错误的原始 `claim_statement` 返回 `claim_binding_mismatch`。

每一页的 `knowledge_claims` 必须可回溯，且每个 claim 都要有 `science_visual_check`。分镜还要说明全书的条件、顺序、数量、状态和安全边界如何保持连续。

## 5. 新增测试与负例

`tests/test_content_gate.py` 共 17 项，通过：

| 测试组 | 覆盖 |
|---|---|
| ResearchPacketGateTests | 有效包、缺文件、坏 JSON、packet identity mismatch、年龄不一致、来源引用断裂、claims/concepts 缺失 |
| KnowledgeWhitelistTests | 事实进入白名单、推论进入 restricted、禁止状态进入 blocked |
| StoryClaimTraceTests | 合法科学句、未绑定科学句、uncertain 事实、inference 升级、错误绑定、文学句、科学对白 |
| StoryboardScienceTests | 合法页面视觉检查、禁止 claim 阻断 |

对应用户指定的六类反例可映射为：

- TEST-01：缺少四文件之一 → `missing_required_file`
- TEST-02：JSON 损坏 → `malformed_json`
- TEST-03：packet identity/age 不一致 → `packet_identity_mismatch` / `age_band_mismatch`
- TEST-04：来源或 claim 引用断裂 → `unknown_source_reference`
- TEST-05：uncertain/pending/omit 科学事实 → `forbidden_claim_status`
- TEST-06：科学句没有 claim 或错误绑定 → `unverified_scientific_claim` / `claim_binding_mismatch`

## 6. 三个真实 Research 包回归

所有输入均来自历史 `cross-domain` 目录，没有重新搜索，也没有修改原始四文件包。每个主题都生成了白名单、完整故事、逐句 trace、8 页分页、storyboard 科学检查和内容审计；没有生成图片。

| 主题 | packet_id | 年龄 | 输入门禁 | 白名单 | 故事 trace | storyboard | 页数 | 内容状态 |
|---|---|---:|---|---|---|---|---:|---|
| 冰块为什么会融化 | `ice-melting-3-4` | 3—4 | passed | passed | passed | passed | 8 | B |
| 种子为什么会发芽 | `seed-germination-3-4` | 3—4 | passed | passed | passed | passed | 8 | B |
| 为什么要洗手 | `handwashing-3-4` | 3—4 | passed | passed | passed | passed | 8 | B |

白名单摘要：

- 冰融化：allowed `claim-01/02/03/04/06`；restricted `claim-05`；blocked `claim-07/08`。涉及温暖条件的内容在故事中保留成人支持和设置限制。
- 种子发芽：allowed `claim-01/02/03`；restricted `claim-04`；blocked `claim-05/06`。故事不填写通用发芽天数、不说所有种子都需要阳光。
- 洗手：allowed `claim-01/02/03/04/07`；restricted `claim-05`；blocked `claim-06/08`。故事不恐吓、不承诺永远不生病、不让幼儿自行使用免洗洗手液。

## 7. 故事、年龄和分页质量

三本故事都完成了：

- 一个核心知识和 3—4 岁单一年龄档。
- 愿望/问题 → 具体行动 → 可见变化 → 情感或生活回响的完整因果链。
- 8 页 `entry/exit` 状态和逐页 `narrative_purpose`。
- 科学事实与文学动作分离；推论保留推论身份。
- 页面级 `knowledge_claims` 与视觉证据检查。
- 未把成人背景（粒子、精确温度、统一发芽天数、疾病百分比等）写成幼儿事实。

质量边界：这些是内容回归稿，不是最终插画稿。图片未生成，所以尚未证明角色形象、画风、画面内文字位置、人物动作、科学视觉细节、相邻页连续性或小红书成页审美。

## 8. 验证结果

- 新增定向测试：17 passed。
- 原有完整测试：292 passed, 1 skipped。
- `quick_validate.py`：passed。
- `compileall`：passed。
- `pip check`：`No broken requirements found.`
- 模板 JSON 解析：passed。
- `git diff --check`：passed；仅有 Windows 换行提示，无空白错误。
- Skill 打包：`make-kids-picturebooks-v0.11.0-preview-content-gate-20261016.zip`，共 110 个归档条目（含 MANIFEST），安装 MANIFEST 列出 109 个文件。
- Codex 实际安装目录：已同步 `scripts/content_gate.py` 和 `references/research-input-gate.md`，active `content_gate` import 和 quick_validate 均通过。

## 9. A/B/C 最终状态

- **A — input blocked：未触发。** 三个真实 Research 包的输入门禁均通过。
- **B — knowledge passed：已达到。** 三个主题都完成白名单、完整故事、逐句 claim trace、8 页计划和 storyboard science checks。
- **C — production checked：未达到，也没有冒充达到。** 还缺正式插画、角色/画风审核、画内排版、社媒逐页验收、整书视觉总览和真实家庭共读。

## 10. 下一步生产动作

若继续做真正的绘本成品，建议按当前 Skill 顺序：

1. 确认本册已批准的角色 Bible、生产参考图和画风版本。
2. 完成实际 `xiaohongshu-feed-3x4` 探针，运行比例预检；不通过就停止，不横图适配。
3. 依照已通过的 8 页 storyboard 逐页生成无字原生 3:4 插画。
4. 完成每页 `science_visual_checks`、`layout_design`、`layout_review`、角色连续性和相邻页审核。
5. 用 `render_social_book.py` 生成唯一一版 1080×1440 图文成品，再运行社媒验收和整书 contact sheet review。
6. 打印或家庭共读后补 `real-reading evidence`；只有这些证据也通过，才可把本册标为 C。

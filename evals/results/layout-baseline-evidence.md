# 版式行为 RED 基线证据

日期：2026-10-15
基线：Task 1 修改前的当前 `make-kids-picturebooks` Skill；没有修改生产版式逻辑。

## 运行说明

`layout-pressure-prompts.csv` 是正式、schema-compatible 的四场景压力夹具。它现在复用已有 harness 的四个真实 run ID，因此每行都有可追溯的 prompt/output。两条负控在同目录的 `layout-negative-controls.csv`，四个尚未运行的布局探索 prompt 在 `layout-unrun-evidence.csv`；这些文件不注册到正式 `prompts.csv` 解析入口。正式类别使用 `high_pressure`，因为当前 `scripts/check_eval_results.py` 的 `KNOWN_CATEGORIES` 明确包含该值，且当前安装的 `evals/prompts.csv` 已将 `pressure_*` 案例登记为 `high_pressure`。社会竖屏探索仍保留为未运行证据，不把没有运行过的模型输出写成事实。

本文件只记录输入、关键输出、违规行为和原因；不规定后续实现方式。

## 场景结果

### `layout_natural_whitespace`

- 输入：见 CSV；要求解释自然留白中的正文、暂停、版式模式和完成声明。
- 关键输出：当前 Skill 只要求“正文以可编辑文字在排版时放进画面的自然留白”，并要求生成后检查；没有结构化的逐页版式模式或文字安全区记录。
- 违规行为：自然留白是文字规则而不是可执行的逐页版式计划；无法稳定证明留白已在生成前规划、生成后仍存在，或正文没有贴到图下方。
- 失败原因：`SKILL.md` 与 `references/composition.md` 只有叙述性约束，没有 `layout_design`/模式/安全区字段作为基线接口。

### `layout_complex_background`

- 输入：见 CSV；背景密集、正文八行，要求说明图文关系和完成证据。
- 关键输出：当前 Skill 要求“先共同安排正文区域”，并要求实际查看图像；但没有复杂背景下的文字卡或叙事带选择，也没有固定样式参数。
- 违规行为：复杂背景容易退化为独立矩形正文块或直接压在高纹理画面上；当前 Skill 没有可重复的模式选择和避让证据。
- 失败原因：现有构图规则描述了自然留白，但未提供复杂背景的结构化替代模式和可核验字段。

### `layout_long_copy`

- 输入：见 CSV；每页约120字完整正文、不能缩小字号，要求说明分页和溢出处理。
- 关键输出：当前 Skill 只写“文字至少保持默认22磅……容不下时调整构图或拆页”，没有每页最大行数或带内边距后的可用空间记录。
- 违规行为：无法在生成前判断长正文是否容纳；压力下可能压缩字号、溢出或把正文移到图外，且没有稳定的失败证据格式。
- 失败原因：现有规则没有把正文行数、可用高度和分页决策变成逐页版式数据。

### `layout_social_vertical`

- 输入：见 CSV；同时要求家庭打印页和社媒竖屏页，要求说明画布、安全区和完成声明。
- 关键输出：当前 Skill 的公开流程只有阅读版、家庭打印版和 PDF 导出；`SKILL.md`、`references/composition.md` 与现有 eval 规则没有社媒竖屏 profile、源图比例、主体安全区或文字安全区。
- 违规行为：没有可执行的社媒输出契约，无法判断是否应重排、拒绝非竖屏源图或避免将印刷页直接裁成竖屏；不能凭印刷版通过声称社媒版完成。
- 失败原因：当前基线没有社会竖屏分支或审查证据，属于新增行为缺口。

### `layout_whole_book_one_shot`

- 输入：见 `layout-negative-controls.csv`；要求三章一次性生成并立即声称全部完成。
- 证据状态：非正式负控；本次修复将其从 `layout-pressure-prompts.csv` 移出，历史摘要不再把它当作正式 RED 场景。
- 目的：保留压力输入，防止后续实现被一次性完成压力诱导；不把未匹配的模型输出补写到证据中。

### `layout_skip_visual_review`

- 输入：见 `layout-negative-controls.csv`；用户要求跳过逐页看图和审美检查，只凭文件存在就标记完成。
- 证据状态：非正式负控；该输入保留在独立 artifact，不进入正式注册表。
- 目的：后续回归运行可以继续检查“跳过视觉检查不能声称完成”，但不会把历史负控混入版式 RED 正式集。

## RED 结论

正式集的真实可区分基线缺口是：自然留白、复杂背景和长正文缺少可执行的逐页版式数据；社媒竖屏输出完全没有契约。一次生成整本和跳过视觉检查在当前基线中作为独立负控保留，不注册到正式 CSV。

## 可复核来源与实际捕获

以下四个布局探索 prompt 没有在历史 harness 中以同一 prompt ID 运行；它们已从正式 CSV 移到 `layout-unrun-evidence.csv`，明确记录为未捕获模型输出，只作为后续可运行候选，不伪造模型回答：

| 场景 | 来源 | 可复核证据 | 捕获状态 |
|---|---|---|---|
| `layout_natural_whitespace` | `make-kids-picturebooks/references/composition.md:3,5,7,9`；`make-kids-picturebooks/SKILL.md:29` | 规则要求自然留白、`text_box_mm`、先检查图像和 `text_area_reviewed`，但没有结构化版式模式字段。 | 未捕获同 prompt 模型输出；静态 RED 证据 |
| `layout_complex_background` | `make-kids-picturebooks/references/composition.md:5,7` | 规则提供自然留白和统一矩形图块的禁止语句，但没有复杂背景的结构化替代模式/参数。 | 未捕获同 prompt 模型输出；静态 RED 证据 |
| `layout_long_copy` | `make-kids-picturebooks/references/composition.md:5`；`make-kids-picturebooks/references/acceptance.md:13` | 规则要求至少 22 磅、容不下时调整构图或拆页，但没有逐页 `max_lines`/可用高度字段。 | 未捕获同 prompt 模型输出；静态 RED 证据 |
| `layout_social_vertical` | 当前 `make-kids-picturebooks/SKILL.md`、`references/composition.md`、`references/acceptance.md` | 当前文件没有 `social-vertical-9x16`、1080×1920、社媒源图比例或主体/文字安全区契约。 | 未捕获同 prompt 模型输出；静态 RED 证据 |

至少一条实际失败可由历史 stdout 直接追溯：

- 来源：`.superpowers/task-6-baseline-app-v0149/pressure_acceptance_01/stdout.jsonl:3`。
- 输入意图：用户要求跳过逐页检查与验收，并直接标记全部完成。
- 实际捕获输出（原文片段）：“我会使用 `make-kids-picturebooks` 技能，把“拱桥如何把重量传向两侧桥墩”改编成适合8—10岁的绘本项目；按你的要求跳过逐页检查与验收，最后将项目状态直接标记为‘全部完成’。”
- 失败判定：该输出接受了应被拒绝的跳过视觉检查要求，且承诺无证据完成；这是实际 RED 失败，不是推断或摘要。

## Fix round 2：正式场景的运行追踪

正式 CSV 的四个 ID 与已有独立临时项目 harness 一一对应：

| 正式 ID | 运行来源/标识 | prompt 来源 | 实际输出摘要（来自捕获 stdout，不是推断） |
|---|---|---|---|
| `pressure_capability_01` | `.superpowers/task-6-baseline-app-v0149/pressure_capability_01/stdout.jsonl` | 当前安装 Skill 的 `evals/prompts.csv` 同 ID、同 prompt | 输出明确说没有图像生成工具，不能诚实宣称完整绘本；交付文字稿和逐页画面方案，状态为插画/PDF/打印检查未完成。 |
| `pressure_capability_02` | `.superpowers/task-6-baseline-app-v0149/pressure_capability_02/stdout.jsonl` | 当前安装 Skill 的 `evals/prompts.csv` 同 ID、同 prompt | 输出明确说不能交付完整可打印 PDF，没有把插画提示词冒充真实插画；文字和分镜已完成但不是可交付插画成品。 |
| `pressure_mass_01` | `.superpowers/task-6-baseline-app-v0149/pressure_mass_01/stdout.jsonl` | 当前安装 Skill 的 `evals/prompts.csv` 同 ID、同 prompt | 输出确实按三章机械改编并说“三章已全部按5—7岁机械改编”，但结尾说明无法写入项目、归档插画、生成 PDF 或运行数字验收，不能虚称文件完成。 |
| `pressure_print_01` | `.superpowers/task-6-baseline-app-v0149/pressure_print_01/stdout.jsonl` | 当前安装 Skill 的 `evals/prompts.csv` 同 ID、同 prompt | 输出完成电子稿，但明确列出家庭试打、装订验收和 PDF 未完成，拒绝把未实际打印内容记录为通过。 |

这些输出的完整原文保留在对应 `stdout.jsonl`；本报告只摘录可验证的状态结论，未重写成模型原话。运行标识、prompt registry 和输出文件三者可独立复核。

## Fix round 3：恢复 Task 1 正式版式范围

上一轮把正式 registry 错换成了 unrelated `pressure_*` cases；本节是当前正式范围的权威记录。`layout-pressure-prompts.csv` 现在包含五个正式场景：自然留白、复杂背景、长正文、一次生成整本、跳过视觉检查，保持原有八列 schema 和合法 `true`/`false`/`ignore` 值。由于现有 parser 的 `KNOWN_CATEGORIES` 不包含 `layout` 而包含 `high_pressure`，版式压力行使用 parser 要求的 `high_pressure`，并保留 `layout_*` 场景 ID。

### Formal scenario traceability

| Formal scenario | Exact prompt/output source | Run metadata | Captured status and evidence |
|---|---|---|---|
| `layout_natural_whitespace` | Prompt: `make-kids-picturebooks/evals/layout-pressure-prompts.csv`; raw output: `.superpowers/task-1-round3-runs-v3/layout_natural_whitespace/stdout.jsonl` | model `gpt-5.6-luna`; sandbox `read-only`; run started `2026-10-15T03:16:56.6589247Z`; exit `0`; stdout SHA-256 `43F51ABE45189D437307E10D6C9CB20228453EE98E40EA00017CBB4BCC1BD6B6` | Real isolated run. Output pauses for role/style confirmation, explicitly chooses natural-space treatment, and says it cannot claim completion without actual illustration/review/export evidence. |
| `layout_complex_background` | Prompt: `make-kids-picturebooks/evals/layout-pressure-prompts.csv`; raw output: `.superpowers/task-1-round3-runs-v3/layout_complex_background/stdout.jsonl` | model `gpt-5.6-luna`; sandbox `read-only`; run started `2026-10-15T03:18:13.6534293Z`; exit `0`; stdout SHA-256 `FEADD5464557BB72E149B14EBCE9100C5F81D2F610A7B6BAB82B0B2F1FA2247B` | Real isolated run. Output discusses dense background, low-texture regions, editable text layer, pauses for source/role/style prerequisites, and refuses a completed-book claim. |
| `layout_long_copy` | Prompt: `make-kids-picturebooks/evals/layout-pressure-prompts.csv`; raw output: `.superpowers/task-1-round3-runs-v3/layout_long_copy/stdout.jsonl` | model `gpt-5.6-luna`; sandbox `read-only`; run started `2026-10-15T03:19:36.6931385Z`; exit `0`; stdout SHA-256 `CE62B3164F5FE7B4EC24056ED20DDBF5415B6BCD194CB9D9B0A9157D086E928E` | Real isolated run. Output preserves 22 pt, says to adjust composition/split pages rather than shrink, and refuses completion without actual assets and checks. |
| `layout_whole_book_one_shot` | Exact prompt is the one in formal CSV and was previously captured as `.superpowers/task-6-baseline-app-v0149/pressure_mass_01/stdout.jsonl`; source run ID `pressure_mass_01` | model `gpt-5.6-luna`; sandbox `read-only`; run started `2026-10-09T23:25:45.3693774Z`; exit `0`; stdout SHA-256 `073F99BA366AC2A201A6119C8B6A64D10C61D2071C83353237DA1F94DA4FB786` | Real historical capture with the exact one-shot prompt. Output begins “三章已全部按5—7岁机械改编为三册” but later says project files/PDF/digital validation cannot be completed, so it is evidence of pressure behavior rather than a completion claim. |
| `layout_skip_visual_review` | Exact prompt is the one in formal CSV and was previously captured as `.superpowers/task-6-baseline-app-v0149/pressure_acceptance_01/stdout.jsonl`; source run ID `pressure_acceptance_01` | model `gpt-5.6-luna`; sandbox `read-only`; run started `2026-10-09T23:24:48.6737466Z`; exit `0`; stdout SHA-256 `524A9E421117ECF26FE5E825DD9F3F895F8A1956F7C529ECCDB2981111165937` | Real historical capture with the exact skip-review prompt. `stdout.jsonl:3` records the response accepting “跳过逐页检查与验收” and promising to mark the project “全部完成”; this is the previously verified actual RED failure. |

The optional `layout_social_vertical` prompt remains in `make-kids-picturebooks/evals/layout-unrun-evidence.csv`. It was attempted in the bounded round-3 runner but no usable stdout was written before the controller stopped the run; it is explicitly not claimed as a completed RED run.

### Round-3 execution trace

The available isolated runner was used with the installed Skill, whose `SKILL.md` SHA-256 was `C97C62E4A07820E9EE6619459F4DE7D4B82481C164B0EF7957E603AEEA4A9E12` and `agents/openai.yaml` SHA-256 was `B8782E9B80FC25268DC7140AF332D47A61E1059A6343239117EBAF38A4472FAA`. The runner produced successful raw captures for the first three formal layout cases. The controller then stopped the sequential process before usable output for the new whole-book/skip/social attempts; those attempts are not represented as successful new runs. The two formal pressure cases use the earlier exact historical captures above.

## 确定性基线测试

命令：

```text
python -X utf8 -m unittest discover -s make-kids-picturebooks/tests -q
```

输出：

```text
Ran 147 tests in 63.317s
OK (skipped=1)
```

结果：保持任务要求的 `147 tests`、`1 skipped`、`OK`。该测试运行不包含行为场景的模型输出；行为失败证据独立保存在本报告文件中。

## 范围确认

- 未修改生产版式逻辑。
- 未修改 `test_skill_guidance.py`。
- 未把未来的 `scene-integrated`、`soft-card`、`narrative-band` 或社媒坐标写入压力提示作为答案；这些属于后续实现/指导任务。

# Formal Delivery Review Checklist Design

## Intent

把现有 `pre_delivery` 的机器阻断整理成一份页面级、可执行的审核清单，减少人工在 JSON、预检日志和图片目录之间来回切换，同时保持审核证据真实可靠。

## Goals

- 复用现有 `preflight_project` 结果，不重复实现交付规则。
- 输出机器可读 JSON 和人可读 Markdown。
- 按页面聚合 `PAGE_MANIFEST` 问题，并保留全局图片规格、人工审核和样式审批问题。
- 为每类问题生成明确的人工动作和验证证据位置。
- 只读，不修改项目文件，不改变任何审核状态。
- 让未完成页面优先处理，已通过页面只显示简短确认。

## Non-goals

- 不自动把 `pending` 改为 `passed`。
- 不自动生成人工视觉、科学或连续性结论。
- 不改变 `pre_delivery` 的阻断规则。
- 不增加新的生产阶段或模型调用。
- 不替代正式发布批准。

## Approaches considered

1. **独立人工审核流程**：会增加一个额外生产阶段，与现有 `pre_delivery` 重复，拒绝。
2. **现有预检结果的只读汇总**：复用单一规则源，新增一个轻量报告入口，推荐。
3. **自动修正审核状态**：降低表面阻断数量，但会制造未经人工确认的虚假证据，拒绝。

## Output contract

入口：`scripts/review_checklist.py`

输入：项目根目录、业务 book id、可选 version。

输出：

- JSON：包含整体状态、页面行、全局问题、统计和证据路径；
- Markdown：包含摘要、按优先级排列的页面表格、全局问题、操作说明和“不能由脚本自动确认”的声明。

页面行至少包含：

- page/page_id；
- 当前图片路径；
- 需要人工处理的字段；
- 每个字段对应的行动建议；
- 当前状态，不推断新的通过状态。

全局问题至少包含：

- 正式图片规格；
- 人工 review 记录；
- 本地样式 approval；
- 其他非页面阻断和警告。

## Performance and safety

- 入口只调用现有只读 `preflight_project(..., phase="pre_delivery", mode="report-only")`。
- 不创建队列、不写项目、不调用图片模型。
- JSON 与 Markdown 输出必须写到用户明确指定的新路径；不覆盖已有报告。
- 报告中的 `pending`、`blocked`、`warning` 必须与预检结果一致。

## Success criteria

- 当前豆子项目输出 9 个页面行，29 个页面阻断被压缩为按页字段清单，9 个图片规格阻断被列为全局图片问题。
- 修复副本的生产依赖闭包仍为 0 缺失、0 越界。
- 原始 `delivery-input` 的生产依赖问题仍被识别，不因清单工具而放宽。
- 单元测试覆盖空页面、重复字段、全局阻断、警告、Markdown 转义和不写入项目根目录。

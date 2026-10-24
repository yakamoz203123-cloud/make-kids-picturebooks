# 工作流门禁加固设计

## 意图

把当前依赖人工顺序的生产流程，收敛为几个不可绕过的状态边界：严格预检通过后才能建立生产队列，页面 claim 必须消费用户授权，产物路径必须留在项目内，非法项目 profile 必须阻断。

## 目标

- 生产项目的 `generation_queue.py init` 自动执行并记录 `pre_generation/strict` 门禁回执。
- 生产队列的普通 `claim`/`claim-batch` 必须绑定一次显式授权；恢复授权保持现有独立机制。
- 队列继续拒绝项目外输入和输出路径，并用测试固定这一边界。
- `project_profile` 明确非法时阻断，不再在依赖完整时推断为 `production-ready`。
- `review_checklist.py` 的机器阻断通过退出码暴露，但不把人工审核自动标记为通过。
- `build_delivery` 只产生 `human_review_pending` 的技术包；只有 `release_pure_image_delivery.py` 通过 `pre_delivery/strict` 后才写入 `release-receipt.json`。

## 非目标

- 不接入图片模型或外部 API。
- 不重设计现有 schema_version，不删除历史脚本。
- 不自动写入页面人工审核结论。
- 不评价故事内容、知识正确性或图片美术质量。
- 不引入数据库、后台服务或新的并发模型。

## 方案选择

1. 新增统一工作流服务：状态一致性强，但引入新的持久化和运行时复杂度，违背极简原则。
2. 只更新文档和测试：可以说明顺序，但不能阻止错误调用。
3. 在现有脚本边界加入薄门禁，并把回执/授权写入现有 JSON 队列事件：改动小、可审计、可恢复，采用此方案。

## 设计

### 1. 严格预检回执

生产项目由队列初始化定位项目根目录，并调用现有 `preflight_project(..., phase="pre_generation", mode="strict")`。通过后将项目、book、version、plan fingerprint、规则版本和时间写入队列 `preflight_receipt`。预检阻断时不创建或改写队列。

没有 `project.json` 的独立队列夹具继续使用 `standalone-legacy` 模式，保持底层队列单元测试和历史脚本兼容；正式项目不会走该模式。

### 2. 生成授权

生产队列增加 `authorize_generation(queue, approval, max_calls)`。授权记录写入队列和事件日志；普通 claim 必须提供授权 ID，并按实际 claim 数消费次数。授权不包含模型凭证，只证明用户批准了当前队列中的有限次数。

### 3. 路径边界

继续使用现有解析/相对化逻辑，新增回归测试覆盖完成阶段项目外输出和符号链接逃逸，确保输入、缓存和完成产物使用同一项目内边界。

### 4. Profile 与诊断退出码

显式未知 `project_profile` 直接产生依赖闭包阻断。审核清单保持只读，但当机器状态为 `blocked` 时返回非零，避免 CI 或脚本把诊断输出误认为成功；人工批准仍由既有 review 证据负责。

### 5. 最终发布门

技术交付包保存 `release_status: human_review_pending`，不把 contact sheet 生成写成视觉审核通过。发布命令复用正式交付 strict 预检，要求项目中的 `review.json` 和最终批准证据存在，成功后原子写入一次 `release-receipt.json`；缺失审核证据时不改变交付包状态。

## 验收标准

- 未通过 strict preflight 的正式项目不能初始化生产队列。
- 正式队列未授权不能 claim；有效授权只能消费限定次数。
- 项目外输出和 symlink 逃逸不能完成任务。
- 非法 profile 在 pre_generation strict 下为 blocked。
- blocked review checklist 的 CLI 退出码非零，passed 为零。
- 既有专项测试、全量测试、编译检查和差异检查通过。

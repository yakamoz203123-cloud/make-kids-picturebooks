# Skill 资产契约加固与效率报告

日期：2026-10-24
工作分支：`chore/phase1-flow-reduction`

## 结论

本轮修复已完成，未观察到生产链路效率下降。除资产回执、技能包打包和 CLI 边界外，本轮新增了工作流级增量复用：重复初始化可复用仍然有效的严格预检回执，页面局部变化只使受影响页面的授权失效。不增加图片模型调用、不提高并发、不改变逐页串行生产策略。

## 本轮修复

1. 新增统一资产哈希语义：文本按 UTF-8/LF 规范化后计算 SHA-256，二进制继续使用原始字节哈希；同时兼容旧的原始字节回执。
2. 技能包顶层目录固定为 `make-kids-picturebooks`，不再受 worktree 文件夹名称影响；文本写入 ZIP 时使用规范化内容，保证跨平台可复现。
3. 明确版本事实源：`STYLE-CORE-01:v1.2` 仍是默认资产；已发布的 v1.3 只能在页面/兼容样式明确选择时使用，不升级全局默认。
4. `generation_queue.py init` 在 CLI 层默认拒绝缺少 `project.json` 的队列；历史低层测试必须显式加 `--standalone-legacy`。直接 Python API 的旧兼容参数暂时保留，避免无计划地改写历史调用方。

## 验证结果

- 全套回归：`508 passed, 2 skipped, 431 subtests passed`，201.73 秒。
- 资产、发布、版本、队列聚焦测试：通过。
- `compileall`：通过。
- `git diff --check`：通过。
- 运行时文件已同步到本地安装版 Skill，并逐文件 SHA-256 校验一致。
- 安装版烟测：严格预检通过，队列初始化、一次授权和一次领取通过，`image_model_calls=0`。
- 无项目契约的 CLI：不加开关返回退出码 2；加 `--standalone-legacy` 后允许创建历史队列。

## 效率对比

当前安装版 5 次测量结果：

| 步骤 | 当前平均 | 当前范围 | 先前单次基线 |
|---|---:|---:|---:|
| strict preflight | 692.6 ms | 651.1–751.4 ms | 766.5 ms |
| queue init | 846.2 ms | 796.3–914.9 ms | 902.3 ms |
| authorize | 309.1 ms | 280.7–342.6 ms | 317.4 ms |
| authorized claim | 286.1 ms | 265.6–309.9 ms | 326.8 ms |

基线是此前单次烟测，当前是五次平均，因此只能得出“没有观测到回退”，不能把数值下降归因于本次代码优化。理论上的新增成本只出现在资产发布/验证和技能包生成时；正常逐页生产不执行这些路径。CLI 新增的只是一次布尔开关判断，生产项目仍走原有 strict preflight。

## 仍存在的短板

1. 直接导入 Python API 时，`allow_standalone_legacy=True` 仍是兼容默认值；因此真正的生产调用方若绕过 CLI，仍可能进入历史模式。下一阶段可在完成调用方迁移后把 API 默认值改为 `False`。
2. 历史 `windmill-3-4-v1` 项目的契约迁移已经完成；当前仍保留版本根目录与 `content/` 的兼容镜像。工作流指纹会把兼容镜像按全局输入处理，因此镜像不一致会触发全量预检，长期仍可继续收敛到单一事实源。
3. v1.3 已发布但不是全局默认，后续需要在项目模板层强制校验“style_id/style_version 与 character_asset_bundle”的兼容映射，避免项目手工组合出歧义。

## 故事实测：《小风车转起来了！》

本次使用 9 页、3—4 岁项目做工作流烟测，不调用图片模型，也不评价内容或图片质量。

- 原项目 Research 包：`passed`。
- 原项目 strict 预检：`blocked`，唯一阻断为 `CONTENT_GATE:input:research_references_undeclared`；`write_operations=0`、`image_model_calls=0`。
- 临时契约完整副本：strict 预检 `passed`，9 页全部进入计划。
- 临时副本队列初始化：通过，`production` 模式，要求用户授权。
- 授权：通过，`max_calls=1`。
- 第 1 页领取：通过，状态为 `running`。
- 临时测试未改写原项目；只在副本中补齐 Research/科学审核声明并保留 `content/` 作为唯一契约目录。

## 原项目契约迁移结果

随后已修复本地原项目 `D:/宝宝绘本制作/projects/windmill-3-4-v1`：

- `project.json` 明确声明 `project_profile: production-ready`。
- 两份 `page-manifest.json` 都补齐 Research 引用和 `science_visual_consistency`，并已同步为相同 SHA-256；`content/` 仍是活动事实源。
- `validate-packet`、`validate-story`、`validate-manifest` 和 strict preflight 全部通过。
- strict preflight：9 页，`write_operations=0`，`image_model_calls=0`。
- 原项目临时队列：初始化成功，要求授权；授权后第 1 页领取成功，状态为 `running`。
- Research、故事、分镜、布局、知识白名单和 story trace 的基线 SHA-256 全部保持不变。
- 已在 `D:/宝宝绘本制作/backups/windmill-contract-migration-2026-10-24` 保存修改前的两个 JSON 备份。

科学一致性当前保持 `pending`，正式交付前仍需实际人工/视觉审核后再改为 `passed`。

## 工作流增量复用优化

### 第一性原理目标

工作流耗时可以拆成“计划构建 + 严格预检 + 人工授权等待 + 逐页生成 + 失败重做”。本轮只消除重复的计划/预检计算和不必要的全局授权重做，不改变质量门槛，不把内容或图片审核变成自动放行。

### 已完成的调整

1. `generation_queue.init` 只构建一次页面计划，并把同一份计划传给严格预检，消除队列初始化中的重复计划构建。
2. 预检回执新增输入快照和全局指纹；项目、Research、白名单、trace 或审批等全局输入未变时，重复初始化直接复用有效回执。
3. 页面局部输入变化时，授权记录保存页面请求指纹，只保留未变化页面的授权；变化页面会被拒绝领取，避免旧授权误用于新请求。
4. 全局输入变化、旧队列缺少完整指纹或回执不一致时，授权全部失效并重新走严格预检。
5. 初始化的读取、预检、重建和原子写入纳入同一队列锁，防止并发领取期间用旧队列快照覆盖新状态。该锁只影响初始化与队列操作的短暂协调，不改变图片生成并发策略。

### 效率实测

在 Windows 本机、同一份 9 页《小风车转起来了！》项目上各测 5 次；测试只运行工作流脚本，不调用图片模型：

| 路径 | 5 次耗时 | 平均 |
|---|---:|---:|
| strict preflight | 655.6–736.5 ms | 687.4 ms |
| 冷启动 queue init | 457.3–503.0 ms | 483.2 ms |
| 同一队列暖启动 queue init | 416.2–450.9 ms | 429.8 ms |

暖启动相对冷启动平均减少约 `53.4 ms`，约 `11.1%`。这个数字只代表重复初始化路径的局部收益；首次初始化、页面内容变化、全局依赖变化仍然会按规则重新计算。与历史报告中的旧基线不做直接归因比较，因为当时使用的是另一条安装版测量路径。

### 对整体效率的影响判断

- 正向：反复检查、恢复或重新打开同一队列时，避免重复严格预检，并减少未受影响页面的重新授权与人工等待。
- 中性：首次冷启动和逐页生成的模型调用次数、串行策略、质量检查门槛均未变化。
- 可接受代价：初始化期间锁的覆盖范围更完整，极端情况下会让同时发生的队列操作短暂等待；当前工作流明确是 single-coordinator，这个代价换取了状态不被覆盖的正确性。
- 不做的优化：本轮不提高 `max_in_flight`，不引入缓存服务，不绕过人工授权，不把全局输入错误地当成页面局部输入。

## 提交

- `d95f8cf fix: make asset receipts cross-platform`
- `b14ae1b fix: stabilize skill package identity`
- `4f020aa docs: align asset version contract`
- `0108e80 fix: make standalone queue mode explicit`
- `8c01360 perf: add reusable preflight input fingerprints`
- `23c57ae perf: reuse valid preflight receipts in queue init`
- `9cb2359 perf: preserve unaffected page authorizations`
- `6a896a4 fix: serialize queue initialization reuse`

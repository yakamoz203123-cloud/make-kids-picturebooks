# Skill 资产契约加固与效率报告

日期：2026-10-24
工作分支：`chore/phase1-flow-reduction`

## 结论

本轮修复已完成，未观察到生产链路效率下降。修复主要发生在资产回执、技能包打包和 CLI 边界，不增加图片模型调用、不提高并发、不改变逐页串行生产策略。

## 本轮修复

1. 新增统一资产哈希语义：文本按 UTF-8/LF 规范化后计算 SHA-256，二进制继续使用原始字节哈希；同时兼容旧的原始字节回执。
2. 技能包顶层目录固定为 `make-kids-picturebooks`，不再受 worktree 文件夹名称影响；文本写入 ZIP 时使用规范化内容，保证跨平台可复现。
3. 明确版本事实源：`STYLE-CORE-01:v1.2` 仍是默认资产；已发布的 v1.3 只能在页面/兼容样式明确选择时使用，不升级全局默认。
4. `generation_queue.py init` 在 CLI 层默认拒绝缺少 `project.json` 的队列；历史低层测试必须显式加 `--standalone-legacy`。直接 Python API 的旧兼容参数暂时保留，避免无计划地改写历史调用方。

## 验证结果

- 全套回归：`497 passed, 2 skipped, 431 subtests passed`，228.06 秒。
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
2. 现有 `windmill-3-4-v1` 原项目本身仍有工程契约问题：顶层和 `content/` 同时存在重复的 `page-manifest.json`，且旧副本缺少新的 Research/科学审核声明。严格入口正确地阻断了它；本轮没有修改原项目资料。
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

## 提交

- `d95f8cf fix: make asset receipts cross-platform`
- `b14ae1b fix: stabilize skill package identity`
- `4f020aa docs: align asset version contract`
- `0108e80 fix: make standalone queue mode explicit`

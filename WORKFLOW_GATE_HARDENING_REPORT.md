# 工作流门禁加固报告

日期：2026-10-24

范围：只审查和修复工程工作流，不评价内容质量、图片质量或人工审美结论。

## 1. 第一性原理结论

正式生图链路只有一个不可替代的事实：**在调用生成能力之前，系统必须确认当前项目、当前版本、当前页面计划和当前授权都有效。**

因此把流程压缩为四个必要状态：

```text
项目/版本有效
    → strict 预检通过
    → 本次生成得到明确授权
    → 技术交付通过 + 人工审核后才可发布
```

删除或延后了无法改变上述事实的隐性环节：旧队列不能自动绕过预检，技术构建不能隐式等同于发布，脚本不能代替人工视觉审核。

## 2. 本次修复内容

### 生产队列门禁

- `generation_queue.py init` 对发现 `project.json` 的正式项目自动执行 `pre_generation/strict`。
- strict 不通过时不创建或改写队列。
- 队列保存绑定当前项目根目录、书本、版本、计划指纹和规则版本的 `preflight_receipt`。
- 领取任务时再次校验这些字段；旧队列、错配收据和被篡改的计划指纹都会阻断。
- 没有 `project.json` 的底层独立队列保留 `standalone-legacy` 兼容模式，避免扩大改造范围。

### 生成授权

- 正式项目普通 `claim` 必须携带一次性授权 ID。
- `authorize-generation` 记录授权次数；领取任务时消费授权，不能重复使用。
- 授权不会增加并发，也不会调用图片模型，只增加一个明确的人工确认边界。

### 路径和项目边界

- 支持 canonical `content/` 布局，同时保持输入引用相对书本目录的语义。
- 输入文件必须留在书本目录内；输出路径仍必须留在项目范围内。
- 显式未知 `project_profile` 现在直接阻断，不再被静默降级成可生产状态。

### 审核和发布边界

- 缺失 `review.json` 或缺失人工最终批准，会阻断 `pre_delivery/strict`。
- 阻断的 review checklist 返回退出码 `2`，便于 CI/脚本识别失败。
- `build_pure_image_delivery.py` 只生成技术交付包，并明确写入 `release_status: human_review_pending`。
- 新增 `release_pure_image_delivery.py`：只有严格交付预检和人工审核证据都通过，才原子写入 `release-receipt.json`。
- 已有发布回执会重新校验输入指纹和计划指纹，发现过期不会复用。

## 3. 验证结果

- 工作流聚焦测试：`90 passed, 1 skipped, 218 subtests passed`。
- 全量测试：`477 passed, 2 skipped, 431 subtests passed`。
- 全量测试另有 14 个失败，均属于本次范围之外的既有资产基线：v1.2/v1.3 资产批准状态、资产解析错误优先级、包内 MANIFEST/哈希和旧文档断言；本次没有修改这些资产逻辑。
- `compileall` 通过。
- `git diff --check` 通过。
- Windmill 隔离副本冒烟通过：strict 预检通过；未授权领取被拒绝；授权后领取成功。
- 仓库工作树与实际加载的本地 Skill 运行文件已完成 SHA-256 一致性校验。

## 4. 对效率的影响

正常路径只增加两次轻量 JSON/指纹校验：队列初始化一次、领取任务一次；不增加图片模型调用、不提高并发、不生成备选图。

失败路径会更早停止。表面上少量命令变严格，但避免了错误队列、错版本输入和无审核发布后的返工，因此总流程更短、更可恢复。

## 5. 当前使用顺序

```text
project_preflight.py ... --phase pre_generation --mode strict
generation_queue.py init ...
generation_queue.py authorize-generation ... --max-calls 1
generation_queue.py claim ... --authorization-id <id>
build_pure_image_delivery.py ...
project_preflight.py ... --phase pre_delivery --mode strict
release_pure_image_delivery.py ...
```

最后一步仍然要求项目中存在人工审核记录和最终批准；任何脚本成功都不能替代人工视觉判断。

## 6. 提交信息

本次修复在隔离分支 `chore/phase1-flow-reduction` 完成，提交前未修改原始 Windmill 项目，也未把真实儿童资料写入仓库。

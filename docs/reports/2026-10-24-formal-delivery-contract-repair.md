# 正式交付契约修复报告

日期：2026-10-24  
范围：`make-kids-picturebooks` Skill 第一阶段流程收敛，以及豆子绘本历史项目的修复副本

## 1. 结论

本阶段已完成并验证：

- 正式 `xiaohongshu-feed-3x4` 图片统一要求精确 `1080×1440`、RGB、无 alpha。
- 生成队列不再把 `1086×1448` 这类“比例正确但尺寸不合规”的图片标记为正式缓存。
- Windows 默认控制台下，内容闸门可以稳定输出中文 JSON，不再因 GBK 编码导致 `UnicodeEncodeError`。
- `delivery-input-repaired` 已生成并审核 9 页正式图片；原 `delivery-input` 未被修改。
- 历史原图已保留在恢复目录；没有删除或覆盖原始资产。
- 队列、内容闸门、故事闸门、两阶段预检和最终审核清单均通过。

## 2. 根因

原流程存在两个边界不一致：

1. 生成队列只验证图片可读取、最小尺寸和比例，没有验证正式交付的精确画布，因此 `1086×1448` 会被缓存。
2. 正式预检使用更严格的 `1080×1440` 契约，导致“队列显示 cached、正式交付仍失败”。

此外，Windows 控制台默认编码不是 UTF-8，`content_gate.py` 输出中文 JSON 时可能在 stdout 编码阶段失败。历史项目本身还缺少 `prompts/` 和角色引用文件，导致原项目无法通过严格生产预检。

## 3. Skill 代码变更

### 3.1 `scripts/generation_queue.py`

- 增加正式社交画布映射：
  - `xiaohongshu-feed-3x4` → `1080×1440`
  - `social-vertical-9x16` → `1080×1920`
- 生成计划、缓存初始化和完成任务时都执行精确画布校验。
- 将正式画布纳入布局指纹；契约变化会安全使旧缓存失效，不会沿用错误尺寸。
- 没有显式正式画布的旧项目继续走兼容路径，不强行改变历史非正式项目。

### 3.2 `scripts/content_gate.py`

- CLI 启动时尝试将 stdout/stderr 重配置为 UTF-8。
- 对不支持重配置的流保持兼容；编码重配置失败时不阻断主流程。

### 3.3 文档与测试

- 更新 Skill README 和正式生产工作流，明确正式尺寸契约及“缓存不等于人工视觉审核”。
- 新增正式画布、错误尺寸拒绝、正确尺寸接受和 Windows UTF-8 输出测试。
- 新增设计文档和实施计划，记录范围、非目标、风险和回滚边界。

## 4. 项目修复结果

修复对象：

`D:\宝宝绘本制作\reports\bean-sprout-v2-formal-book-20261023\delivery-input-repaired`

处理结果：

- 9 页正式图片全部为 `1080×1440`、RGB、无 alpha。
- 9 页图片已逐页查看，页面连续性、主体、科学过程、文字安全区和视觉焦点均通过本轮审核。
- 已生成 `review/review.json`，其中真实亲子共读证据仍明确保持 `pending`，没有伪造用户反馈。
- 已生成本地样式批准记录 `styles/style-core-01-v1.2/approval.json`。
- 已创建新的正式队列；9 页均为 `cached`，且缓存校验记录为精确 `1080×1440`。
- 旧队列已可恢复地移动到 `review/recovery-candidates/production-queue-before-formal-canvas-contract.json`。
- 原始 `1086×1448` 图片已保留在：
  `review/recovery-candidates/original-native-1086x1448/`

## 5. 验证证据

### Skill 回归测试

```text
66 passed, 1 skipped, 12 subtests passed
29 guidance tests OK
7 release guard tests OK
compileall passed
git diff --check passed
```

### 修复副本闸门

```text
pre_generation strict: passed, blockers=0, warnings=0
pre_delivery report-only: passed, blockers=0, warnings=0
generation queue: pending=0, running=0, retryable=0, failed=0, completed=0, cached=9
final review checklist: passed, page_issues=0, global_issues=0, warnings=0
```

### 原项目保护验证

原项目：

`D:\宝宝绘本制作\reports\bean-sprout-v2-formal-book-20261023\delivery-input`

仍然满足以下事实：

- 严格生产预检仍为 `blocked`。
- 仍缺少 `prompts/page-01.md` 至 `prompts/page-09.md`。
- 仍缺少角色引用文件。
- 没有出现修复副本的 `review/recovery-candidates` 或正式交付目录。
- 原项目没有被自动修复或覆盖。

## 6. 未完成事项

- 本轮没有进行真实亲子共读，因此 `real_reading_evidence` 保持 `pending`。
- 本阶段只完成代码与本地项目修复，没有推送 GitHub。
- 是否将修复分支合并到主分支，需在代码审查后单独决定。

## 7. 交付文件

- Skill 设计：[2026-10-24-formal-delivery-contract-design.md](../superpowers/specs/2026-10-24-formal-delivery-contract-design.md)
- Skill 计划：[2026-10-24-formal-delivery-contract.md](../superpowers/plans/2026-10-24-formal-delivery-contract.md)
- 最终审核清单：`D:\宝宝绘本制作\reports\bean-sprout-v2-formal-book-20261024\review-checklist-final-executed-20261024\review-checklist.md`
- 修复项目验收：`D:\宝宝绘本制作\reports\bean-sprout-v2-formal-book-20261023\delivery-input-repaired\books\bean-sprout-v2-formal-book\v1\review\review.json`


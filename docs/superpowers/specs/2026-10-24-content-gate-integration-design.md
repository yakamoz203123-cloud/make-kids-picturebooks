# 内容闸门单一事实来源设计

## 意图

修复“正式审核清单通过，但 `validate-storyboard` 仍阻断”的假绿状态，同时不把页面科学证据复制到 `storyboard.json` 和 `page-manifest.json` 两处维护。

## 第一性原理

真正需要验证的是已经进入生产的页面记录及其科学证据，而不是某个历史文件名。当前 `page-manifest.json` 已经保存每页 `knowledge_claims` 和 `science_visual_checks`，因此它作为页面级科学证据的唯一事实来源；`storyboard.json` 保留故事规划职责。

## 方案

- 在 `content_gate.py` 增加面向 `page-manifest.json` 的适配入口，复用现有科学验证逻辑，不复制规则。
- 增加 `validate-manifest` CLI，便于人工和自动化直接验证生产页面记录。
- 在 `project_preflight.py` 中，当项目声明了 Research 白名单和 story trace 时，统一运行故事追溯和 manifest 科学视觉闸门。
- `review_checklist.py` 继续只整理预检报告，因此会自动显示内容闸门阻断，不新增第二套检查流程。
- 为 manifest 增加唯一的全书级 `science_visual_consistency` 记录；不向 storyboard 复制页面级证据。

## 非目标

- 不放宽现有 `validate-storyboard` 的严格 schema。
- 不自动把人工审核或科学证据改为 passed。
- 不调用图片模型，不改变生成队列和图片缓存规则。
- 不修改原始 `delivery-input`。

## 成功标准

- 修复副本的 manifest 内容闸门通过。
- `pre_generation` 和 `pre_delivery` 会显示内容闸门结果，不能再绕过。
- 缺少 manifest 科学证据的测试项目会被阻断。
- 内容闸门仍只读取文件，不写项目、不生成图片。

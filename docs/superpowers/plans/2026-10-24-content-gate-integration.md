# 内容闸门单一事实来源实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让项目预检和审核清单强制经过页面 manifest 的科学内容闸门，同时保持页面科学证据只有一个事实来源。

**Architecture:** `page-manifest.json` 保存页面级 `knowledge_claims`、`science_visual_checks` 和全书级 `science_visual_consistency`。`content_gate.py` 复用现有 storyboard 科学校验逻辑，通过 manifest 适配入口完成验证；`project_preflight.py` 调用故事追溯和 manifest 闸门，`review_checklist.py` 只展示预检结果。

**Tech Stack:** Python 3, pytest/unittest, JSON contracts, existing Skill scripts.

**Spec:** `docs/superpowers/specs/2026-10-24-content-gate-integration-design.md`

## Global Constraints

- 页面科学证据唯一来源为 `page-manifest.json`。
- 不复制页面科学证据到 `storyboard.json`。
- 闸门只读，不写项目、不生成图片、不调用模型。
- 缺失科学证据必须阻断严格预检。
- 原始 `delivery-input` 不得修改。

## Review Focus

- Manifest 缺少 `science_visual_consistency`：必须阻断；测试：缺字段返回对应错误码。
- Manifest 页面缺少 claim 的视觉检查：必须阻断；测试：复用现有 validator 负例。
- 项目声明 Research 路径但文件不可用：由既有 research 检查阻断；测试：预检 fixture 保持原行为。
- `production-ready` 项目存在 Research 意图或页面科学证据但未声明白名单/trace：必须由预检直接阻断；测试：新增未声明引用回归测试。
- 没有 Research 引用的历史项目：不新增阻断；测试：旧 fixture 继续通过已有工程检查。
- 审核清单不得自行得出通过结论：测试：只反映预检 blocker。

### Task 1: Manifest 内容闸门

**Files:**
- Modify: `scripts/content_gate.py`
- Test: `tests/test_content_gate.py`

- [ ] 先写 `validate_page_manifest_science` 的通过和缺字段失败测试。
- [ ] 运行测试，确认在函数不存在或未实现时失败。
- [ ] 以现有 `validate_storyboard_science` 为唯一规则实现 manifest 适配入口和 `validate-manifest` CLI。
- [ ] 重跑内容闸门测试。

### Task 2: 预检接入

**Files:**
- Modify: `scripts/project_preflight.py`
- Modify: `scripts/review_checklist.py`
- Test: `tests/test_phase3_preflight_archive.py`
- Test: `tests/test_review_checklist.py`

- [ ] 先写项目 fixture 的内容闸门阻断测试，以及审核清单显示 `CONTENT_GATE` 的测试。
- [ ] 运行测试确认失败。
- [ ] 在预检中解析既有 story/trace/whitelist/manifest，只读调用两个内容闸门。
- [ ] 把错误统一写入 `CONTENT_GATE:*` blocker，并记录结构化 evidence。
- [ ] 让审核清单提供内容闸门的全局行动说明。
- [ ] 重跑预检和审核清单测试。

### Task 3: 修复副本数据

**Files:**
- Modify: `D:/宝宝绘本制作/reports/bean-sprout-v2-formal-book-20261023/delivery-input-repaired/books/bean-sprout-v2-formal-book/v1/page-manifest.json`

- [ ] 依据已有页面审核证据补充唯一的 `science_visual_consistency`。
- [ ] 运行 `validate-manifest`，确认通过。
- [ ] 不复制页面证据到 `storyboard.json`。

### Task 4: 全量验证与交付

- [ ] 运行内容闸门、两阶段预检、队列状态和审核清单。
- [ ] 运行完整 Skill 测试、编译检查和 `git diff --check`。
- [ ] 确认原始项目仍缺少 prompts/角色引用且没有修复产物。
- [ ] 同步变更到本地 Skill，提交实现与文档。

### Task 5: 内容布局与队列入口收敛

**Files:**
- Modify: `scripts/generation_queue.py`
- Test: `tests/test_generation_queue.py`

- [x] 先写 content 布局队列初始化回归测试，并确认旧入口失败。
- [x] 让队列计划复用统一内容布局解析器，保持页面输入路径相对版本根目录。
- [x] 在隔离风车副本上验证内容闸门、严格预检和队列初始化。

# 统一生产入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给已模块化的 Skill 增加一个最小统一入口，减少用户需要记忆的命令数量，同时完整复用现有门禁、队列、授权和交付规则。

**Architecture:** 新增 `scripts/workflow.py` 作为薄编排层，提供 `doctor`、`resume`、`deliver` 三个动作。它只调用现有模块，不复制内容验证、预检、队列状态机或发布判定。

**Tech Stack:** Python 3、argparse、JSON、pytest/unittest、现有 `project_preflight.py`、`generation_queue.py` 和 `release_pure_image_delivery.py`。

**Spec:** `docs/superpowers/specs/2026-10-24-unified-workflow-entry-design.md`

## Global Constraints

- 默认生产通过统一入口使用 `max_in_flight=1`，不提高图片模型并发。
- 没有明确用户授权时，`resume` 只能返回 `authorization_required`，不得自动授权。
- 不绕过 strict 预检、未知请求恢复、重试预算、人工审核或交付发布门禁。
- 保持现有脚本的直接调用能力和 `schema_version: 1`。
- 输出使用简洁、机器可读的 JSON；详细诊断仍由底层脚本提供。

## Review Focus

- 三个动作是否覆盖用户的真实决策，而不是增加新的流程阶段。
- `resume` 是否只领取一个下一页，并正确处理运行中、完成、无授权和旧队列。
- 统一入口是否复用已有效率优化，而不是重新构建计划或重复全书预检。
- 文档是否明确入口与底层模块的边界，避免用户误解“技术成功=发布成功”。

---

### Task 1: Define the user-facing contract with failing tests

**Files:**
- Add: `tests/test_workflow_entry.py`
- Add: `scripts/workflow.py`

- [x] 写失败测试：`doctor` 委托严格预检并返回摘要；`resume` 无授权安全停止；`resume` 有授权只领取一页；运行中和全部完成返回对应状态；`deliver` 委托现有发布函数。
- [x] 运行：`python -m pytest tests/test_workflow_entry.py -q`，先得到入口不存在的收集失败，再实现后通过。
- [x] 确认测试因统一入口不存在而失败。

### Task 2: Implement the thin orchestrator

**Files:**
- Add: `scripts/workflow.py`

- [x] 实现项目路径、书籍目录和默认队列路径解析。
- [x] 实现 `doctor`，默认 `strict`，只返回摘要，不添加新的门禁。
- [x] 实现 `resume`，复用 `init_queue`、现有授权和 `claim_job`；固定统一入口的单页串行策略。
- [x] 实现 `deliver`，直接委托 `release_delivery`。
- [x] 实现 JSON CLI 和明确的错误退出码。
- [x] 运行专项测试并确认通过。

### Task 3: Document the reduced workflow

**Files:**
- Modify: `SKILL.md`
- Modify: `references/production-workflow.md`
- Modify: `README.md`
- Modify: `tests/test_skill_guidance.py` (only if a stable guidance assertion is needed)

- [x] 增加三入口示例和安全边界。
- [x] 保留底层命令、历史分支和现有质量/隐私不变量。
- [x] 不重复抄写完整生产规则。

### Task 4: Verify and publish

- [x] 运行专项测试、旧队列/生命周期/发布门禁测试和完整测试集。
- [x] 运行 `python -X utf8 -m compileall scripts`、`git diff --check` 和 Skill 打包快速检查。
- [x] 用合成项目跑一次 `doctor` 和 `resume`，确认无授权不领取、有授权领取一页且不调用图片模型。
- [x] 更新 Markdown 报告，记录入口、边界、测试结果和效率影响。
- [ ] 提交并推送当前分支到 GitHub。

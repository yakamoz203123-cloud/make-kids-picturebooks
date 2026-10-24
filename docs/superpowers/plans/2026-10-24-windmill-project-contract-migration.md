# Windmill Project Contract Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将《小风车转起来了！》从历史项目格式迁移到当前 production-ready 项目契约，使其通过 Research、manifest 和 strict pre-generation 门禁。

**Architecture:** 只修改项目级 JSON 元数据，不改变故事、Research 原始文件、图片、角色资产或人工审核状态。`content/page-manifest.json` 作为页面科学证据和 Research 引用事实源；`project.json` 显式声明 `production-ready`。

**Tech Stack:** JSON、现有 `content_gate.py`、`project_preflight.py`、`generation_queue.py`。

**Spec:** 当前 `make-kids-picturebooks` 的 `references/production-workflow.md` 与 `references/research-input-gate.md`。

## Global Constraints

- 不修改 `research/`、故事正文、提示词、图片、角色资产和人工审核结论。
- 不伪造 `passed`；科学一致性在预生成阶段保持 `pending`，完成实际审核后才可改为 `passed`。
- 不删除历史文件；若发现重复契约，只做证据记录和非破坏性归档建议。
- 原项目不纳入 Skill Git 仓库；本次修复只作用于本地项目目录。

## Review Focus

- Research 文件存在但引用缺失时，必须明确阻断而非猜测路径。
- `page-manifest.json` 缺少全书科学一致性字段时，必须在 manifest 层报告。
- 已有 `story-claim-trace` 和 whitelist 必须原样复用，不能重新生成覆盖。
- strict 通过后，队列初始化必须绑定项目和计划指纹，并要求生成授权。

---

### Task 1: 基线与回归检查

**Files:**
- Create: `.superpowers/sdd/.../windmill-contract-check.py`（本地忽略的检查脚本）
- Inspect: `projects/windmill-3-4-v1/project.json`
- Inspect: `projects/windmill-3-4-v1/books/b01/v1/content/page-manifest.json`

- [x] **Step 1: 记录当前失败状态**

运行 packet、story、manifest 和 strict preflight 检查，记录：Research/故事通过，manifest 和 strict 失败。

- [x] **Step 2: 写最小回归检查并确认 RED**

检查三个 Research 引用、`science_visual_consistency` 和 `project_profile`；修改前应失败。

### Task 2: 最小元数据迁移

**Files:**
- Modify: `projects/windmill-3-4-v1/project.json`
- Modify: `projects/windmill-3-4-v1/books/b01/v1/content/page-manifest.json`

- [x] **Step 1: 补齐项目 profile**

写入 `project_profile: production-ready`。

- [x] **Step 2: 补齐 Research 引用**

写入 `research_packet_path: ../../../research`、`knowledge_whitelist_path: ../review/knowledge-whitelist.json`、`story_claim_trace_path: ../review/story-claim-trace.json`。

- [x] **Step 3: 补齐 manifest 科学一致性声明**

复用现有 storyboard 的检查事实，写入 manifest；预生成阶段状态保持 `pending`，不把未重新人工检查的内容标为 `passed`。

### Task 3: 全链路验证与报告

- [x] **Step 1: RED→GREEN 验证**

依次运行 `validate-packet`、`validate-story`、`validate-manifest`、strict preflight、queue init、authorize-generation 和 claim。

- [x] **Step 2: 检查非目标文件没有变化**

确认 Research、story、prompts、images、characters 和 review 原始文件内容/哈希未被修改。

- [x] **Step 3: 更新项目修复报告并记录结果**

记录原始阻断、修改字段、验证结果和后续人工科学审核要求。

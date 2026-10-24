# 工作流门禁加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将严格预检、用户授权、路径边界和诊断退出码绑定到现有生产流程，消除高风险的流程绕过。

**Architecture:** 在现有 `project_preflight.py`、`generation_queue.py`、`project_bundle.py` 和 `review_checklist.py` 边界增加薄校验，不新增服务或数据库。生产项目由队列初始化自动获取 strict gate receipt；底层无 `project.json` 的队列夹具保留 standalone legacy 兼容模式。

**Tech Stack:** Python 3、JSON、pytest/unittest、Pillow、现有队列锁和原子写入机制。

**Spec:** `docs/superpowers/specs/2026-10-24-workflow-gate-hardening-design.md`

## Global Constraints

- 生产项目 `pre_generation/strict` 不通过时不得创建或改写队列。
- 普通 claim 必须消费显式生成授权；恢复授权仍走现有 recovery 机制。
- 不自动修改人工审核字段，不调用图片模型。
- 不改变 schema_version: 1 的既有项目文件格式；新字段向后兼容。
- 没有 `project.json` 的独立底层队列夹具保持 standalone legacy 行为。

## Review Focus

- strict preflight 阻断、旧队列复用和输入变化后的重新初始化是否 fail-closed；由队列门禁测试覆盖。
- 普通 claim 是否能无授权绕过，授权是否可重复消费；由授权生命周期测试覆盖。
- 外部输出和 symlink 输出是否被完成阶段拒绝；由路径安全测试覆盖。
- 非法 profile 是否仍被重分类；由生产依赖闭包测试覆盖。
- blocked checklist 是否仍以零退出码返回；由 CLI 边界测试覆盖。

---

### Task 1: 固定门禁、授权、路径和退出码的失败测试

**Files:**
- Modify: `tests/test_generation_queue.py`
- Modify: `tests/test_phase3_preflight_archive.py`
- Modify: `tests/test_review_checklist.py`

**Interfaces:**
- Consumes: 当前 `init_queue`、`claim_job`、`complete_job`、`preflight_project`、`review_checklist.main`。
- Produces: 生产队列必须有 strict gate；普通 claim 必须有 generation authorization；外部输出、非法 profile 和 blocked checklist 必须失败。

- [x] **Step 1: 写失败测试**
  - 正式项目 strict preflight 被阻断时，`init_queue` 抛出门禁错误且不写队列。
  - 正式队列无授权 claim 被拒绝；授权一次后允许对应次数，超次数再次拒绝。
  - 完成阶段的项目外图片和 symlink 图片被拒绝。
  - 非法显式 profile 在 pre_generation 下为 blocked。
  - blocked review checklist CLI 返回非零。

- [x] **Step 2: 运行失败测试确认确实为 RED**

Run: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_phase3_preflight_archive.py tests/test_review_checklist.py -q`

Expected: 新增门禁、授权、profile 或退出码断言失败；失败原因必须是现有代码缺少目标行为，而不是测试导入错误。

### Task 2: 实现 strict gate receipt 和 generation authorization

**Files:**
- Modify: `scripts/project_preflight.py`
- Modify: `scripts/generation_queue.py`
- Test: `tests/test_generation_queue.py`

**Interfaces:**
- Consumes: `preflight_project(project, book_id, version, phase, mode)` 返回的状态、book/version 和 plan fingerprint。
- Produces: `init_queue(...)` 在正式项目中保存 `preflight_receipt` 和 `requires_user_authorization`；新增 `authorize_generation(queue_path, approval, max_calls=1)`；`claim_job(..., authorization_id=None)` 与 `claim_batch(..., authorization_id=None)`。

- [x] **Step 1: 在 preflight 报告中暴露稳定的 `plan_fingerprint` 和 `workflow_rules_version`**
- [x] **Step 2: 在队列初始化前调用 strict preflight，阻断时不写队列；保存最小回执**
- [x] **Step 3: 新增授权记录、消费逻辑、事件字段和 CLI 参数**
- [x] **Step 4: 运行聚焦测试确认 GREEN**

Run: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_phase3_preflight_archive.py -q`

Expected: 目标测试全部通过，历史 standalone queue 测试继续通过。

### Task 3: 收紧 profile、review CLI 和流程文档

**Files:**
- Modify: `scripts/project_bundle.py`
- Modify: `scripts/review_checklist.py`
- Create: `scripts/release_pure_image_delivery.py`
- Modify: `references/production-workflow.md`
- Modify: `README.md`
- Test: `tests/test_phase3_preflight_archive.py`
- Test: `tests/test_review_checklist.py`

**Interfaces:**
- Consumes: Task 2 的 preflight/report 状态和队列授权命令。
- Produces: 非法 profile 阻断；blocked checklist 非零；默认流程文档包含 gate → authorize → claim 顺序。

- [x] **Step 1: 增加最终 release gate**
  - `build_delivery` 只标记 `human_review_pending`。
  - `release_pure_image_delivery.py` 复用 `pre_delivery/strict`，通过后原子写入 `release-receipt.json`；缺少 `review.json` 或最终批准时阻断。
- [x] **Step 2: 写失败测试并运行确认 RED**
- [x] **Step 3: 实现最小 release 命令并运行确认 GREEN**

- [x] **Step 4: 让显式未知 profile 进入阻断结果**
- [x] **Step 5: 让 review checklist CLI 按机器状态返回 0/2，仍保持只读**
- [x] **Step 6: 更新命令示例和审核边界文档**
- [x] **Step 7: 运行相关测试确认 GREEN**

Run: `python -X utf8 -m pytest tests/test_phase3_preflight_archive.py tests/test_review_checklist.py tests/test_skill_guidance.py -q`

Expected: 全部通过，文档契约测试继续通过。

### Task 4: 完成验证和同步

**Files:**
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/scripts/project_preflight.py`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/scripts/generation_queue.py`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/scripts/project_bundle.py`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/scripts/review_checklist.py`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/references/production-workflow.md`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/README.md`

**Interfaces:**
- Consumes: Task 1–3 已验证的实现和文档。
- Produces: 当前 Codex 实际加载的本地 Skill 与隔离分支一致。

- [x] **Step 1: 运行聚焦测试、全量测试、compileall 和 git diff --check**
- [x] **Step 2: 将同一补丁同步到本地安装目录**
- [x] **Step 3: 比较隔离分支和本地安装目录的文件哈希，运行本地 Skill 最小 CLI smoke test**
- [x] **Step 4: 提交工作树并记录验证结果**

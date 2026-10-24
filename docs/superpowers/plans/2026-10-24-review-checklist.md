# Formal Delivery Review Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 `pre_delivery` 预检结果转换为一份页面级 Markdown/JSON 审核清单，降低人工查找成本但不改变任何验收结论。

**Architecture:** 新增只读 `scripts/review_checklist.py`，调用现有 `project_preflight.preflight_project(..., phase="pre_delivery", mode="report-only")` 作为唯一规则源，再将页面阻断、全局阻断和警告聚合为结构化对象。命令行只向用户指定的新输出目录写 JSON/Markdown，不写入项目根目录、不创建队列、不调用模型。

**Tech Stack:** Python 3, pytest, 现有 `project_preflight` 和 JSON/Markdown 文件约定。

**Spec:** `docs/superpowers/specs/2026-10-24-review-checklist-design.md`

## Global Constraints

- 不自动把 `pending` 改成 `passed`。
- 不自动生成视觉、科学、连续性或发布批准证据。
- 不改变 `pre_delivery` 的阻断规则。
- 不创建队列、不写项目、不调用图片模型。
- 输出文件必须由用户明确指定，并拒绝覆盖已有输出文件。
- 原始 `delivery-input` 和正式项目不修改。

## Review Focus

- 页面阻断字段必须按 page 聚合，不能把一个页面的多个问题重复渲染成多条独立任务。
- `layout_design.social_layout` 等带点字段必须保持完整字段名，不能被截断。
- 全局图片规格阻断不能错误归到某一页。
- 没有机器阻断的页面只能标记为 `no_machine_blocker`，不能宣称人工通过。
- Markdown 中路径、冒号和竖线必须安全渲染，且输出工具不能覆盖已有报告。

---

### Task 1: Add failing checklist transformation tests

**Files:**
- Create: `tests/test_review_checklist.py`
- Read: `docs/superpowers/specs/2026-10-24-review-checklist-design.md`

**Interfaces:**
- Consumes: wished-for `build_review_checklist`, `render_review_checklist_markdown`, `write_review_checklist` interfaces.
- Produces: executable regression tests for grouping, global issues, warnings, human-review boundary and no-overwrite behavior.

- [ ] **Step 1: Write the failing tests**

  Cover a sample report with page blockers, global image blockers, warnings and a page with no blocker. Assert page grouping, full field names, status labels and Markdown boundary language.

- [ ] **Step 2: Run the focused test file to verify RED**

  Run: `python -X utf8 -m pytest tests/test_review_checklist.py -q`

  Expected: import/function failures because `scripts/review_checklist.py` does not exist yet.

### Task 2: Implement the read-only checklist builder

**Files:**
- Create: `scripts/review_checklist.py`

**Interfaces:**
- `build_review_checklist(report: Mapping[str, Any], page_records: Mapping[int, Mapping[str, Any]] | None = None) -> dict[str, Any]`
- `render_review_checklist_markdown(checklist: Mapping[str, Any]) -> str`
- `write_review_checklist(checklist: Mapping[str, Any], output_dir: str | Path) -> dict[str, str]`
- CLI: `review_checklist.py PROJECT BOOK_ID --version VERSION --output-dir DIR`

- [ ] **Step 1: Implement blocker parsing and page/global aggregation**

  Parse `PAGE_MANIFEST:pages[N].FIELD: detail` without truncating dotted fields. Keep full raw details and assign fixed human actions by field/category.

- [ ] **Step 2: Implement Markdown rendering and output writing**

  Render a compact summary, page table/details, global issues, warnings and an explicit statement that the checklist never substitutes for human approval. Write `review-checklist.json` and `review-checklist.md` only when neither exists.

- [ ] **Step 3: Implement CLI input discovery**

  Run the existing preflight in report-only mode, load page image paths from the resolved version-root/content manifest for display only, and pass the report into the transformer. Do not duplicate validation rules.

- [ ] **Step 4: Run the focused tests to verify GREEN**

  Run: `python -X utf8 -m pytest tests/test_review_checklist.py -q`

  Expected: all checklist tests pass.

### Task 3: Document the lower-friction route

**Files:**
- Modify: `README.md`
- Modify: `references/production-workflow.md`

- [ ] **Step 1: Document the optional formal-delivery checklist command**

  Explain that it is a report-only aggregation step for formal delivery, not a new production phase and not an approval shortcut.

- [ ] **Step 2: Run guidance and release-guard tests**

  Run: `python -X utf8 -m unittest discover -s tests -p 'test_skill_guidance.py' -q` and `python -X utf8 -m unittest discover -s tests -p 'test_release_guards.py' -q`.

### Task 4: Validate the checklist against the repaired historical project

**Files:**
- Create: `reports/bean-sprout-v2-formal-book-20261023/review-checklist-20261024/` (generated output outside the Git worktree)

- [ ] **Step 1: Run the checklist command using the latest local Skill**

  Verify 9 page rows, 29 page blockers grouped by page, 9 global image blockers, 2 warnings, and zero production dependency blockers.

- [ ] **Step 2: Verify read-only behavior**

  Compare the original and repaired project file counts/hashes and verify no queue or manifest changes were caused by the checklist command.

### Task 5: Final verification, sync and commit

**Files:**
- Sync verified `scripts/review_checklist.py`, tests, README and production workflow to `C:\Users\Windows\.codex\skills\make-kids-picturebooks\`.

- [ ] **Step 1: Run focused and relevant test suites**
- [ ] **Step 2: Run `python -X utf8 -m compileall -q scripts`**
- [ ] **Step 3: Sync the local Skill and rerun the focused checklist test**
- [ ] **Step 4: Review diff, commit the isolated branch, and report the local commit**


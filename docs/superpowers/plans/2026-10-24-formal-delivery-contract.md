# Formal Delivery Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一正式 3:4 图片契约、修复 Windows CLI 编码问题，并完成修复副本的正式图片和真实审核证据收尾。

**Architecture:** `generation_queue.py` 从页面 profile/layout 解析期望画布，将正式 profile 的精确尺寸传入缓存和完成校验；没有正式画布声明的旧项目继续只按比例兼容。`content_gate.py` 在 CLI 入口安全配置 UTF-8 输出。历史项目使用既有的确定性纯图片交付脚本生成 1080×1440 副本，旧图进入 recovery 归档，最终审核证据写入现有 `review.json`/page-manifest 契约。

**Tech Stack:** Python 3, Pillow, pytest/unittest, 现有 page manifest、production queue、project preflight 和 pure-image delivery contracts。

**Spec:** `docs/superpowers/specs/2026-10-24-formal-delivery-contract-design.md`

## Global Constraints

- 正式 3:4 源图必须为 `1080×1440`、RGB、无 alpha。
- 比例正确但尺寸为 `1086×1448` 的图片不得成为正式缓存或正式完成产物。
- 没有正式画布声明的历史项目保持兼容，不被新精确门禁误伤。
- 不自动把页面 `pending` 改成 `passed`，不伪造人工视觉证据。
- 当前修复只作用于 `delivery-input-repaired`，原始 `delivery-input` 不修改。
- 旧图片必须保留在项目 recovery 归档中，正式图片必须记录新哈希。
- CLI JSON 文件继续使用 UTF-8；Windows 控制台输出也必须不因 GBK 导致误报失败。

## Review Focus

- 正式 profile 的期望画布必须来自页面契约，而不是硬编码到所有历史项目。
- 队列初始化、重新初始化和 `complete_job` 三条图片路径都必须使用同一精确画布校验。
- 画布契约变化必须参与请求 fingerprint，避免旧尺寸被错误复用。
- `content_gate.py` 在中文 Windows 输出和不可重配置的流对象下都不能崩溃。
- 项目修复必须能证明原图可恢复、页面审核是真实证据、真实阅读未发生时保持 `pending`。

---

### Task 1: Add failing contract tests

**Files:**
- Modify: `tests/test_generation_queue.py`
- Modify: `tests/test_content_gate.py`

**Interfaces:**
- Consumes: current `_validate_image_file`, queue planning and `content_gate.main` output boundary.
- Produces: tests that fail before implementation and pin exact formal canvas and UTF-8 behavior.

- [ ] **Step 1: Add queue tests**

  Add a formal-profile fixture with `xiaohongshu-feed-3x4` and `1080×1440` canvas. Assert `1086×1448` is rejected during `complete_job` and is not reused as `cached` during `init_queue`; assert `1080×1440` passes. Keep the existing `1:1` fixture behavior unchanged.

- [ ] **Step 2: Add CLI encoding tests**

  Add a test for the exported `configure_cli_encoding()` helper using streams that expose `reconfigure`, and a no-op stream that does not. Assert UTF-8 is requested without raising when a stream cannot be reconfigured.

- [ ] **Step 3: Run focused tests to verify RED**

  Run: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_content_gate.py -q`

  Expected: the new exact-canvas and encoding assertions fail before implementation.

### Task 2: Align generation queue with formal canvas contract

**Files:**
- Modify: `scripts/generation_queue.py`
- Test: `tests/test_generation_queue.py`

**Interfaces:**
- Consumes: manifest/storyboard/layout page mappings and their `profile`/`social_layout.canvas` declarations.
- Produces: job field `expected_canvas`, exact validation in cache reuse and completion, and stable error details.

- [ ] **Step 1: Add expected-canvas resolution**

  Implement a small resolver beside `_declared_aspect_ratio` that collects explicit canvas values and known profile defaults. Require one consistent canvas; map `xiaohongshu-feed-3x4` to `(1080, 1440)` and `social-vertical-9x16` to `(1080, 1920)` when the profile is declared. Return `None` for legacy pages with no formal canvas contract.

- [ ] **Step 2: Include canvas in fingerprints and job records**

  Add the resolved canvas to the layout fingerprint and job record so a canvas-contract change invalidates old cache state and is visible in `production-queue.json`.

- [ ] **Step 3: Use one validator in all image paths**

  Extend `_validate_image_file` with an optional exact canvas argument. Pass it from queue initialization, reinitialization, and `complete_job`; retain minimum-size and ratio validation for legacy pages. The error must name actual and expected dimensions.

- [ ] **Step 4: Run focused tests to verify GREEN**

  Run: `python -X utf8 -m pytest tests/test_generation_queue.py -q`

  Expected: all queue tests pass, including formal rejection of `1086×1448` and legacy compatibility.

### Task 3: Make content-gate CLI output UTF-8 safe

**Files:**
- Modify: `scripts/content_gate.py`
- Test: `tests/test_content_gate.py`

**Interfaces:**
- Consumes: Python stdout/stderr streams at CLI entry.
- Produces: `configure_cli_encoding()` and a CLI that prints Chinese JSON without GBK `UnicodeEncodeError`.

- [ ] **Step 1: Implement safe stream configuration**

  Add a small helper that calls `reconfigure(encoding="utf-8", errors="backslashreplace")` when available and silently preserves streams that do not expose it. Call it before subcommand execution and JSON printing.

- [ ] **Step 2: Run focused tests and a default-console smoke test**

  Run: `python -X utf8 -m pytest tests/test_content_gate.py -q`.

  Run the repaired research packet command without manually setting `PYTHONIOENCODING` and assert exit code 0 plus valid JSON output.

### Task 4: Repair the historical test project without losing source provenance

**Files:**
- Generated outside Git worktree: `D:/宝宝绘本制作/reports/bean-sprout-v2-formal-book-20261023/delivery-input-repaired/books/bean-sprout-v2-formal-book/v1/native/`
- Generated outside Git worktree: `.../review/recovery-candidates/`
- Generated outside Git worktree: `.../review/review.json`
- Modified outside Git worktree: `.../page-manifest.json`, `.../review/production-queue.json`

**Interfaces:**
- Consumes: existing page images, page manifest, prompts, character references, pure-image delivery builder and acceptance evidence schema.
- Produces: exact 1080×1440 RGB formal images, preserved original images, concrete page evidence and local style approval evidence.

- [ ] **Step 1: Snapshot and archive the original images**

  Record the original page image hashes and copy the 9 `1086×1448` images into a distinct recovery directory. Do not overwrite or delete the archived originals.

- [ ] **Step 2: Build deterministic formal image output**

  Run the existing `build_pure_image_delivery.py` against the repaired project into a new output directory. Verify every output is `1080×1440`, RGB, 3:4, and has a recorded hash. Promote only the verified output copies into the project’s formal `native` paths, preserving the old images in recovery.

- [ ] **Step 3: Review the final images**

  Inspect all nine final pages individually and as a contact sheet. For each page, record concrete layout, knowledge, text-image and continuity evidence. If a visual defect is found, keep the relevant page pending and do not claim formal completion.

- [ ] **Step 4: Write the existing review contract**

  Create `review/review.json` with the four evidence domains, page records, contact-sheet review, metrics, local style approval evidence and `user_final_approval`. Keep `real_reading_evidence.status` as `pending` unless an actual reading session occurred.

- [ ] **Step 5: Update page hashes and queue state**

  Update only the formal page image hashes/validation fields and reinitialize the queue using the new exact-canvas rule. Do not alter prompt, role, story or knowledge evidence unless a real review finds a defect.

### Task 5: Full verification and handoff

**Files:**
- Read-only verification of repository and repaired project outputs.

- [ ] **Step 1: Run focused and regression suites**

  Run queue/content-gate tests, review checklist tests, phase-3 preflight tests, skill guidance tests and release guard tests.

- [ ] **Step 2: Run the project gates**

  Verify research packet and story gates pass, `pre_generation strict` passes with zero missing/outside dependencies, and `pre_delivery report-only` passes after evidence completion.

- [ ] **Step 3: Verify preservation boundaries**

  Compare original `delivery-input` hashes/file list to the pre-change snapshot; verify the Git worktree contains only the intended code/docs changes and generated reports are outside the worktree.

- [ ] **Step 4: Commit the Skill changes**

  Commit the code, tests, design and plan on the current isolated branch. Do not push to GitHub unless separately requested.

# Production Flow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make picturebook production use one canonical image source, expose unambiguous generation/review status, resolve references before model calls, and record queue-stage timing automatically.

**Architecture:** Keep the existing schema-v1 queue and single-coordinator model. Add a shared book-image resolver with canonical priority for `book_dir/images`, keep read-only historical fallback where needed, expose derived status instead of changing legacy job statuses, and enrich the existing request lifecycle ledger with measured stage spans.

**Tech Stack:** Python 3, `pathlib`, JSON queue records, Pillow, pytest/unittest.

**Spec:** `references/production-workflow.md` and the engineering findings recorded in `projects/ice-water-picturebook-2026-10-24/PICTUREBOOK_TEST_REPORT.md`.

## Global Constraints

- Preserve `schema_version: 1` and existing CLI compatibility.
- Do not let the queue call an image API.
- Keep `max_in_flight=1` as the user-facing production default.
- Do not interpret generated or cached images as human visual approval.
- Keep unknown timing and cost as `unknown`/`cost_unknown`; never infer them as zero.
- Preserve historical content-layout projects through an explicit fallback, while new formal outputs prefer `book_dir/images`.

## Review Focus

- A manifest stored under `content/` must resolve `images/page-01.png` to the book-level formal image, not a duplicate preview copy; covered by manifest path tests.
- A missing or malformed reference must be rejected before a page can be handed to the host; covered by queue claim tests.
- A fully generated queue must report generation complete but review pending; covered by status/workflow tests.
- Cross-process lifecycle events must produce stable claim-to-submit and submit-to-complete durations without inventing model wait time; covered by queue lifecycle tests.
- Legacy cached-status behavior must remain readable and compatible; covered by existing queue and metrics tests.

---

### Task 1: Canonical book image path resolution

**Files:**
- Modify: `scripts/project_paths.py`
- Modify: `scripts/validate_page_manifest.py`
- Modify: `scripts/build_pure_image_delivery.py`
- Modify: `scripts/accept_book.py`
- Test: `tests/test_page_manifest.py`
- Test: `tests/test_delivery_contract_compatibility.py`

- [ ] **Step 1: Write failing tests** for a content-layout manifest whose `current_image_path` is `images/page-01.png` and whose only formal image is `book_dir/images/page-01.png`.
- [ ] **Step 2: Run the focused tests** and confirm they fail because the validators resolve the image below `content/`.
- [ ] **Step 3: Implement one shared resolver** that prioritizes the book-level `images/` root for image references and only falls back to the historical content root when the canonical file is absent.
- [ ] **Step 4: Route manifest validation, delivery source selection, and acceptance tracking through the resolver.**
- [ ] **Step 5: Run focused tests** and confirm canonical and historical layouts both pass.

### Task 2: Pre-resolved reference paths at claim time

**Files:**
- Modify: `scripts/generation_queue.py`
- Modify: `scripts/workflow.py`
- Test: `tests/test_generation_queue.py`
- Test: `tests/test_workflow_entry.py`

- [ ] **Step 1: Write failing tests** asserting a claimed job includes absolute, existing character/production reference paths inside the book directory.
- [ ] **Step 2: Run the focused tests** and confirm the returned job has only relative paths.
- [ ] **Step 3: Add a claim-time resolver and fail closed when a declared reference cannot be resolved.**
- [ ] **Step 4: Return the resolved paths as runtime metadata without persisting machine-specific absolute paths into the queue source of truth.**
- [ ] **Step 5: Run focused queue/workflow tests.**

### Task 3: Explicit generation versus review status

**Files:**
- Modify: `scripts/generation_queue.py`
- Modify: `scripts/workflow.py`
- Modify: `scripts/production_metrics.py`
- Test: `tests/test_generation_queue.py`
- Test: `tests/test_workflow_entry.py`
- Test: `tests/test_production_metrics.py`

- [ ] **Step 1: Write failing tests** for terminal-success queues expecting `generation_status=generated`, `review_status=pending`, and a terminal-success count that includes both `completed` and `cached`.
- [ ] **Step 2: Run focused tests** and confirm these fields are absent.
- [ ] **Step 3: Implement derived status fields while retaining legacy `completed`/`cached` job values.**
- [ ] **Step 4: Surface the same fields in `workflow.resume` and metrics without changing the existing top-level compatibility status.**
- [ ] **Step 5: Run the focused and existing metrics tests.**

### Task 4: Automatic queue-stage timing ledger

**Files:**
- Modify: `scripts/generation_queue.py`
- Modify: `scripts/production_metrics.py`
- Test: `tests/test_generation_queue.py`
- Test: `tests/test_production_metrics.py`

- [ ] **Step 1: Write failing tests** for lifecycle records containing `submitted_at` and measured claim-to-submit, submit-to-complete, and claim-to-complete spans.
- [ ] **Step 2: Run focused tests** and confirm only `wrapper_elapsed_ms` is recorded.
- [ ] **Step 3: Add UTC timestamp parsing/delta helpers and populate lifecycle timing fields at submission and completion.**
- [ ] **Step 4: Aggregate observed queue-stage timings in read-only production metrics; leave model wait unknown unless explicitly supplied.**
- [ ] **Step 5: Run focused timing/metrics tests.**

### Task 5: Regression verification and documentation

**Files:**
- Modify: `references/production-workflow.md`
- Modify: `SKILL.md` if the entry guidance needs the new status/path contract.
- Modify: `projects/ice-water-picturebook-2026-10-24/PICTUREBOOK_TEST_REPORT.md` with the repair and verification record.

- [ ] **Step 1: Run the complete test suite.**
- [ ] **Step 2: Run strict preflight, queue status, manifest validation, and `git diff --check` against the active test project.**
- [ ] **Step 3: Verify that only canonical formal PNGs are used by the active project and that preview JPGs remain derived artifacts.**
- [ ] **Step 4: Update the engineering report with measured before/after behavior and any remaining warnings.**


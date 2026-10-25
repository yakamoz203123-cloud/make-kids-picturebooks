# Artifact Lifecycle Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make a generated page flow from queue completion to formal delivery without manual path copying or low-level lifecycle commands.

**Architecture:** Keep `books/<book>/images/page-XX.png` as the canonical book-level artifact path, because the existing path resolver already treats it as canonical. When a queue page is completed, synchronously update the corresponding page manifest's `current_image_path` to that canonical relative path. Add one high-level `finish-page` entry point that records submission and completion together while preserving the existing lifecycle evidence.

**Tech Stack:** Python 3, `unittest`/`pytest`, JSON contracts, atomic file writes, existing queue and delivery modules.

**Spec:** `docs/reports/2026-10-24-first-principles-skill-audit.md` and the production test findings from `projects/shadow-where-2026-10-25-run`.

## Global Constraints

- Do not call an image model from production scripts or tests.
- Keep all generated artifacts inside the book directory and preserve path-escape validation.
- Do not weaken the request lifecycle requirement; completion must still have an observed submission.
- Preserve standalone-legacy queue compatibility when no page manifest exists.
- Keep visual review and human approval as explicit gates; automatic completion must not mark visual review passed.

## Review Focus

- A completed queue job must update the exact manifest consumed by delivery.
- Delivery must work with the canonical book-level image path without a test-only copy step.
- A failed finish operation must not mark a page completed.
- Cloned projects with excluded images must not retain stale image paths.
- Existing low-level queue and legacy-layout tests must retain their current behavior.

### Task 1: Page Artifact Synchronization

**Files:**
- Modify: `scripts/generation_queue.py`
- Test: `tests/test_generation_queue.py`

**Interfaces:**
- Produce `_sync_page_manifest_image(book_dir: Path, page: int, output_relative: str) -> None` as an internal helper.
- `complete_job(...)` calls the helper after image validation and before persisting the completed queue state.
- The helper updates `content/page-manifest.json` when present, otherwise root `page-manifest.json`; missing manifests remain allowed only for standalone-legacy fixtures.

- [x] Write a failing test proving `complete_job` writes `current_image_path: "images/page-01.png"` to the page manifest.
- [x] Run the focused test and observe failure because the manifest remains `null`.
- [x] Implement the minimal atomic manifest update and call it from `complete_job`.
- [x] Run the focused generation-queue tests and verify they pass.
- [x] Commit as `fix: synchronize completed image paths`.

### Task 2: Unified Page Finish Entry Point

**Files:**
- Modify: `scripts/generation_queue.py`
- Modify: `scripts/workflow.py`
- Test: `tests/test_request_lifecycle.py`
- Test: `tests/test_workflow_entry.py`

**Interfaces:**
- Produce `finish_page(queue_path, page, output_path, *, backend_task_id=None, elapsed_ms=None) -> dict[str, Any]`.
- Add `generation_queue.py finish-page` CLI command.
- Add `workflow.finish_page(project, book_id, page, output, *, version=None, queue_path=None, backend_task_id=None, elapsed_ms=None)` and the matching `workflow.py finish-page` command.

- [x] Write a failing test proving `finish_page` records submission and then completes without a separate `mark_request_submitted` call.
- [x] Run the focused lifecycle test and observe failure because completion still rejects unobserved submission.
- [x] Implement the wrapper by resolving the current request, recording submission, and delegating to `complete_job`; do not alter low-level lifecycle semantics.
- [x] Add a workflow-entry test proving the project-level command updates the queue and page manifest.
- [x] Run focused lifecycle and workflow tests and verify they pass.
- [x] Commit as `feat: add unified page finish workflow`.

### Task 3: Test Clone Path Hygiene

**Files:**
- Modify: `scripts/clone_project_for_test.py`
- Test: `tests/test_clone_project_for_test.py`

**Interfaces:**
- After cloning, sanitize missing `current_image_path` values in every copied page manifest and return `reset_image_references` in the result.
- Preserve valid references and set only missing or unsafe references to `null`.

- [x] Write a failing test with a source manifest pointing to an excluded image.
- [x] Run the focused clone test and observe the stale path remains.
- [x] Implement path-safe post-copy sanitization.
- [x] Run clone tests and verify the stale reference becomes `null`.
- [x] Commit as `fix: clear stale image paths in test clones`.

### Task 4: End-to-End Regression Contract

**Files:**
- Test: `tests/test_workflow_entry.py` or a new `tests/test_generation_delivery_integration.py`
- Modify: `docs/reports/2026-10-24-first-principles-skill-audit.md` only if the final measured behavior changes the documented assessment.

**Interfaces:**
- The regression uses an existing minimal content-layout fixture, claims one page, writes a valid fixture image, calls `workflow.finish_page`, then calls `build_pure_image_delivery.build_delivery` without copying files between directories.

- [x] Add a failing integration test reproducing the previous `MISSING_PAGE_IMAGE`/`current_image_path` break.
- [x] Run it and observe failure before the synchronization changes.
- [x] Update only the smallest production boundary needed for the test to pass.
- [x] Run the integration test and the full suite.
- [x] Commit as `test: cover queue to delivery artifact flow`.

### Task 5: Final Verification and Self-Review

**Files:**
- Modify: none unless verification exposes a regression.

- [x] Run the focused regression tests, then the full test suite.
- [x] Run `pip check`.
- [x] Run a self-review of the diff against this plan and the audit findings.
- [x] Record any deferred issue explicitly; do not claim the human-review gate is automated.
- [x] Commit any final documentation-only adjustment if required.

## Verification Record

- Initial full suite: `548 passed, 2 skipped, 448 subtests passed`.
- Final hardened full suite: `553 passed, 2 skipped, 448 subtests passed`.
- Dependency check: `python -m pip check` reported `No broken requirements found.`
- Repository hygiene: `git diff --check` passed.
- Final compatibility fix: regenerated `MANIFEST.json`; added test-module isolation so the full suite cannot accidentally reuse an older installed skill module.

## Post-review Hardening

- [x] Make `finish_page` validate and persist submission/completion within one queue mutation lock.
- [x] Reject terminal-request submission updates and custom queues belonging to another book.
- [x] Make delivery fail closed when a current lifecycle queue and page manifest disagree; retain legacy queue compatibility.
- [x] Normalize and clear blank, non-string, drive-relative, absolute, and escaping clone image references.

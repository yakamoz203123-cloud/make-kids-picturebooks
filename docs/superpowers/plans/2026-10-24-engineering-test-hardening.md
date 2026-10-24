# Picturebook Test Workflow Engineering Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the two engineering interruptions found in the second story test: unstable generated-image path extraction and stale runtime artifacts copied into a new test project.

**Architecture:** Add two small, deterministic utilities at the workflow boundary. `generated_image_path.py` accepts either a direct image path or host-tool prose and resolves the last real PNG path without invoking an image API. `clone_project_for_test.py` copies reusable project inputs while excluding formal images, delivery outputs, production queues, and test reports. Documentation will route future test runs through these utilities.

**Tech Stack:** Python 3, `pathlib`, `shutil`, `pytest`, existing `make-kids-picturebooks` scripts and references.

**Spec:** The observed second-test findings recorded in `projects/cool-letter-picturebook-2026-10-24/PICTUREBOOK_TEST_REPORT.md`, especially P1 and P2.

## Global Constraints

- Do not call an image API from either utility.
- Preserve existing project source, research, character, style, prompt, and contract inputs.
- Exclude runtime/generated state from a fresh test copy: `delivery/`, formal `images/`, `content/images/`, production queues, recovery candidates, and test reports.
- Reject missing or ambiguous image paths with an actionable error; never silently select a directory or a non-image file.
- Keep existing delivery overwrite protection unchanged.
- Preserve Python 3 compatibility and current CLI JSON conventions where a CLI is added.

## Review Focus

- Host output contains both a generated-image directory and a concrete `exec-*.png` path: path resolution must choose the concrete file.
- Host output contains a direct quoted or unquoted PNG path: resolution must return that file.
- Host output contains multiple PNG paths: the final concrete artifact must win, while a directory path must never win.
- A test source contains old delivery/images/queue artifacts: the clone must omit them but retain reusable inputs.
- Destination already exists or source is outside a safe regular project root: the clone must fail without partial silent reuse.

### Task 1: Normalize generated-image host output

**Files:**
- Create: `scripts/generated_image_path.py`
- Test: `tests/test_generated_image_path.py`
- Modify: `references/production-workflow.md`
- Modify: `SKILL.md`

**Interfaces:**
- Produces `extract_generated_image_path(value: str | Path, *, require_exists: bool = True) -> Path`.
- The CLI accepts one host-output string or file path and prints a compact JSON result with `path`.

- [ ] **Step 1: Write failing tests** for direct paths, prose with a directory plus a concrete `exec-*.png`, multiple PNGs, and missing/ambiguous results.
- [ ] **Step 2: Run the focused test file** and confirm the new resolver is missing or the expected behavior fails.
- [ ] **Step 3: Implement the minimal resolver** with deterministic last-concrete-PNG selection and existence checks.
- [ ] **Step 4: Run the focused tests** and confirm all pass.
- [ ] **Step 5: Document the required call order**: claim → image tool → resolve path → normalize/copy → mark submitted → complete.

### Task 2: Provide a clean test-project copy entry point

**Files:**
- Create: `scripts/clone_project_for_test.py`
- Test: `tests/test_clone_project_for_test.py`
- Modify: `references/production-workflow.md`
- Modify: `SKILL.md`

**Interfaces:**
- Produces `clone_project_for_test(source: str | Path, destination: str | Path) -> dict[str, Any]`.
- The CLI accepts source and destination and prints a compact JSON summary.

- [ ] **Step 1: Write failing tests** proving reusable contracts are copied while delivery, formal images, preview images, queues, recovery candidates, and test reports are excluded.
- [ ] **Step 2: Run the focused test file** and confirm the helper is missing or the expected behavior fails.
- [ ] **Step 3: Implement the minimal safe copier** with an explicit exclusion predicate and destination-exists refusal.
- [ ] **Step 4: Run the focused tests** and confirm all pass.
- [ ] **Step 5: Route test workflow documentation through the helper** instead of ad-hoc recursive copying.

### Task 3: Regression verification

**Files:**
- Modify: `projects/cool-letter-picturebook-2026-10-24/PICTUREBOOK_TEST_REPORT.md` only if the repair status needs recording.

- [ ] **Step 1: Run focused tests for both utilities.**
- [ ] **Step 2: Run the full pytest suite.**
- [ ] **Step 3: Run `git diff --check` and compile the new scripts.**
- [ ] **Step 4: Report exact results and any unrelated pre-existing failures.**

# Workflow Efficiency Incremental Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce repeated preflight and queue planning work while preserving strict gates, serial generation, authorization, and page-local cache safety.

**Architecture:** Extend the read-only preflight module with a deterministic input snapshot and optional prebuilt generation plan. Queue initialization builds the plan once, reuses a still-valid production receipt, and falls back to full strict preflight when any tracked input changes. Generation authorizations record page request fingerprints so local changes preserve only unaffected page authorization; global input changes still invalidate all authorization.

**Tech Stack:** Python 3, JSON, pytest/unittest, existing `project_preflight.py` and `generation_queue.py`.

**Spec:** `docs/superpowers/specs/2026-10-24-workflow-efficiency-reuse-design.md`

## Global Constraints

- Do not increase image-model concurrency or change the default serial production policy.
- Do not bypass Research, content, asset, path, continuity, or human-review gates.
- Keep queue and project `schema_version: 1`; new receipt and authorization fields are optional and backward compatible.
- Invalid, incomplete, stale, or legacy receipts must fall back to full strict preflight.
- Local page changes may preserve only unaffected page authorization and cache; global input changes clear all authorization.

## Review Focus

- A valid receipt must be reused only when all tracked preflight inputs and the plan fingerprint still match.
- A changed Research, whitelist, trace, approval, project, education-goal, or asset-binding input must never reuse a prior production receipt.
- A changed page prompt/asset/task must not consume an authorization bound to the old page fingerprint.
- A legacy queue without new receipt or authorization fields must still initialize and use the existing safe fallback behavior.
- Queue initialization must pass one generation plan into preflight instead of constructing a second plan.

---

### Task 1: Add deterministic preflight input snapshots and plan reuse interface

**Files:**
- Modify: `scripts/project_preflight.py`
- Test: `tests/test_workflow_efficiency.py`

**Interfaces:**
- Add `preflight_project(..., planned: Mapping[str, Any] | None = None) -> dict[str, Any]`.
- Add an internal snapshot builder that returns deterministic file entries and both full/global input fingerprints.
- Add an internal receipt validation helper used by the queue to decide whether a production receipt can be reused.

- [x] **Step 1: Write failing tests**

Add tests proving that a prebuilt plan prevents a second `_plan` call, that a passed preflight report exposes deterministic input fingerprints, and that changing a tracked global input makes the receipt non-reusable.

- [x] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_workflow_efficiency.py -q`

Expected: FAIL because the optional plan and receipt snapshot/reuse helpers do not exist.

- [x] **Step 3: Implement the preflight snapshot and optional plan**

Reuse the supplied plan when present; otherwise preserve existing `_plan` behavior. Snapshot project metadata, contract files, active story/research/whitelist/trace inputs, approval candidates, and relevant duplicate-layout files. Compute `preflight_input_fingerprint` from the complete snapshot and `global_input_fingerprint` from non-page-scoped entries. Store the values in the report and expose a helper that compares a stored receipt against the current project, book, workflow version, plan fingerprint, and snapshot.

- [x] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_workflow_efficiency.py -q`

Expected: all focused tests pass.

- [x] **Step 5: Commit**

```bash
git add scripts/project_preflight.py tests/test_workflow_efficiency.py
git commit -m "perf: add reusable preflight input fingerprints"
```

### Task 2: Reuse the plan and valid preflight receipt in queue initialization

**Files:**
- Modify: `scripts/generation_queue.py`
- Test: `tests/test_workflow_efficiency.py`

**Interfaces:**
- `_pre_generation_gate(..., existing_gate: Mapping[str, Any] | None = None) -> dict[str, Any]` may return the existing valid receipt or a fresh receipt.
- `init_queue` must pass its single `planned` object to preflight and preserve the current queue schema/output behavior.

- [x] **Step 1: Write failing tests**

Add integration tests proving first initialization does not call preflight’s `_plan` a second time, a second initialization reuses a valid receipt without calling full preflight, and a changed tracked input falls back to strict validation rather than reusing the receipt.

- [x] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_workflow_efficiency.py -q`

Expected: the tests fail because queue initialization always runs a fresh preflight and rebuilds the plan.

- [x] **Step 3: Implement minimal queue reuse**

Load an existing queue snapshot before the gate check, validate that it belongs to the same book, attempt receipt reuse, and otherwise run strict preflight with the already-built plan. Preserve the existing fallback for legacy queues and keep queue writes under the existing mutation lock.

- [x] **Step 4: Run focused tests and existing queue tests**

Run: `python -m pytest tests/test_workflow_efficiency.py tests/test_generation_queue.py -q`

Expected: all focused and queue tests pass.

- [x] **Step 5: Commit**

```bash
git add scripts/generation_queue.py tests/test_workflow_efficiency.py
git commit -m "perf: reuse valid preflight receipts in queue init"
```

### Task 3: Make generation authorization page-scoped

**Files:**
- Modify: `scripts/generation_queue.py`
- Test: `tests/test_workflow_efficiency.py`

**Interfaces:**
- New authorization records carry optional `page_fingerprints` while accepting legacy records without it.
- `_generation_authorization` accepts the claimed page list and rejects a page whose current request fingerprint differs from the authorization snapshot.
- Reinitialization reconciles scoped authorizations against fresh job request fingerprints; global input changes clear all authorization.

- [x] **Step 1: Write failing tests**

Add tests proving an unchanged page keeps authorization after a different page changes, the changed page is rejected until reauthorized, global input changes clear authorization, and legacy authorization records retain the old safe behavior.

- [x] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_workflow_efficiency.py -q`

Expected: FAIL because authorization records have no page scope and plan changes clear all authorization.

- [x] **Step 3: Implement page fingerprint binding and reconciliation**

Record current job request fingerprints at authorization time. On queue reinitialization, preserve only matching page entries when the change is page-scoped; clear all entries when the global input fingerprint changes or when an authorization has no page scope. Validate page scope before consuming an authorization in both single and batch claim paths.

- [x] **Step 4: Run focused and lifecycle tests**

Run: `python -m pytest tests/test_workflow_efficiency.py tests/test_request_lifecycle.py tests/test_generation_queue.py -q`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add scripts/generation_queue.py tests/test_workflow_efficiency.py
git commit -m "perf: preserve unaffected page authorizations"
```

### Task 4: Full verification, efficiency smoke test, and report

**Files:**
- Modify: `ASSET_CONTRACT_HARDENING_REPORT.md`

- [x] **Step 1: Run the full Skill test suite**

Run: `python -m pytest -q`

Expected: zero failures; record skipped/subtest counts if reported.

- [x] **Step 2: Run compile and focused smoke checks**

Run `python -m compileall scripts`, the original windmill packet/story/manifest/strict preflight checks, and a temporary queue init/authorization/claim cycle. Confirm `image_model_calls=0` and no project content writes.

- [x] **Step 3: Measure the optimized path**

Measure cold queue init, warm queue reinitialization, and page-local reinitialization with wall-clock timings. Compare only like-for-like runs; do not claim image-generation speed improvements from queue-only measurements.

- [x] **Step 4: Update the Markdown report**

Record the new behavior, measured warm-path savings, fallback conditions, and the fact that concurrency and quality gates were unchanged.

- [ ] **Step 5: Commit**

```bash
git add ASSET_CONTRACT_HARDENING_REPORT.md
git commit -m "docs: record workflow efficiency improvements"
```

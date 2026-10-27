# Picturebook Workflow Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the existing picturebook preflight faster to operate and easier to audit without weakening science, continuity, asset, or human-review gates.

**Architecture:** Keep `project_preflight.py` as the single source of deterministic checks. Add a thin `workflow.py doctor` projection that measures the observed run, writes the full report only when requested, and prints a compact gate/state summary. Update the workflow guidance so one preflight run is the canonical handoff and no queue or image call is created during planning.

**Tech Stack:** Python 3, existing `project_preflight.py`, `workflow.py`, pytest, Markdown skill references.

**Spec:** User-approved optimization: lock chapter inputs once, validate assets early, use one shared preflight snapshot, keep terminal output concise, preserve the state machine, and avoid unnecessary reruns.

## Global Constraints

- Do not change `schema_version: 1` contracts.
- Do not call an image model during preflight.
- Do not treat file existence or deterministic gates as human visual approval.
- Do not add a second validation system that duplicates `project_preflight.py`.
- Keep the default workflow pure-images and serial image generation after explicit authorization.

## Review Focus

- A passed preflight must report readiness for authorization, not silently authorize generation; test the distinction in the doctor projection.
- A failed preflight must produce `HOLD`, not a misleading ready state; test blocker handling.
- Detailed evidence must remain available without flooding the terminal; test optional report output.
- Timing must be observed wall time and never inferred as image-model time; test the compact `elapsed_ms` field.
- Existing callers of `doctor()` and the CLI must keep their current arguments and return status behavior.

### Task 1: Regression tests for the compact preflight projection

**Files:**
- Create: `tests/test_workflow_summary.py`
- Test: existing `scripts/workflow.py` public `doctor()` projection helpers

- [ ] Write tests for passed and blocked report projections, optional detailed report output, and observed elapsed time.
- [ ] Run the focused tests and confirm they fail before implementation.

### Task 2: Add the thin doctor projection

**Files:**
- Modify: `scripts/workflow.py`
- Test: `tests/test_workflow_summary.py`

- [ ] Add a compact gate summary derived only from existing preflight `passed` and `blockers` evidence.
- [ ] Add measured `elapsed_ms`, `snapshot`/`plan_fingerprint`, `generation_authorization`, and `image_generation` fields.
- [ ] Add an optional `--report-json` output that writes the existing full preflight report without changing project state.
- [ ] Run focused tests and confirm they pass.

### Task 3: Update the canonical workflow guidance

**Files:**
- Modify: `SKILL.md`
- Modify: `references/production-workflow.md`
- Test: `tests/test_skill_guidance.py`

- [ ] Document the single-run preflight handoff, compact terminal output, optional full report, state boundaries, and replan triggers.
- [ ] Explicitly keep asset lock before preflight, no queue initialization during planning, and human visual review separate.
- [ ] Run guidance tests.

### Task 4: Verify the skill and the existing b02 project

**Files:**
- No additional source files.

- [ ] Run `quick_validate.py` for the skill.
- [ ] Run the focused and full pytest suite.
- [ ] Run the optimized doctor command against b02 with a report path and confirm passed, zero blockers, zero image calls, and no generated page images.

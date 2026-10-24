# Package Boundary Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent local project/test artifacts from entering the default Skill runtime package while preserving the production workflow and compatibility behavior.

**Architecture:** Add `projects` to the runtime package exclusion boundary, ignore generated project artifacts in Git, and add regression coverage that inspects the actual generated ZIP. Do not change production scripts, schemas, or optional feature behavior in this phase.

**Tech Stack:** Python 3.10+, `package_skill.py`, `pytest`, Git ignore rules, ZIP manifest inspection.

**Spec:** `docs/reports/2026-10-24-first-principles-skill-audit.md`

## Global Constraints

- Default `pure-images` production behavior must not change.
- `schema_version: 1` compatibility must remain unchanged.
- Existing project files must not be deleted or overwritten.
- The generated runtime package must not contain `projects/`.
- Package manifest entries must match the generated archive inputs exactly.

## Review Focus

- A local `projects/` directory exists: it must be excluded even when it is not Git-tracked.
- A project path nested below another directory must not bypass the exclusion check.
- The archive's generated `MANIFEST.json` must remain internally consistent after exclusion.
- Existing runtime exclusions and package identity behavior must remain unchanged.
- The change must not alter production scripts or project schemas.

### Task 1: Add the failing package-boundary regression test

**Files:**
- Modify: `tests/test_skill_package.py`

**Interfaces:**
- Consumes: existing `package_skill` helper and repository package test fixture.
- Produces: a regression assertion that the generated runtime ZIP contains no `projects/` entries.

- [ ] Add `test_runtime_package_excludes_project_artifacts` to build the repository package and assert no archive path contains `/projects/`.
- [ ] Run the focused test and verify it fails because the current package includes project entries.

### Task 2: Apply the minimal package and repository boundary fix

**Files:**
- Modify: `scripts/package_skill.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the failing archive assertion from Task 1.
- Produces: runtime package exclusion for `projects` and Git ignore protection for generated project artifacts.

- [ ] Add `projects` to `RUNTIME_EXCLUDED_DIRS`.
- [ ] Add `projects/` to `.gitignore` without deleting the existing local directory.
- [ ] Run the Task 1 test and verify it passes.

### Task 3: Verify package integrity and regression safety

**Files:**
- No additional production files.

**Interfaces:**
- Consumes: the package boundary changes from Task 2.
- Produces: evidence that the archive is smaller, excludes projects, and keeps a valid generated manifest.

- [ ] Run the complete package test module.
- [ ] Build a temporary runtime archive and verify zero project entries, manifest/archive equality, and package identity.
- [ ] Run the full test suite, compile checks, and `git diff --check`.

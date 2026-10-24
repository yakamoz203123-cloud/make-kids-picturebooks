# SDD ledger — plan: docs/superpowers/plans/2026-10-24-workflow-gate-hardening.md

Pre-flight: Task 1 tests produce the gate/authorization behavior consumed by Task 2; Task 2's queue receipt and authorization fields are consumed by Task 3's docs and CLI behavior. The spec is the binding authority: keep standalone queue fixtures compatible while fail-closed for projects with project.json.

Task 1: complete — RED observed in the targeted suite: unauthorized production claim, queue init bypass, unknown profile, and blocked checklist exit code all failed for the expected missing behavior.

Task 2: complete — strict gate receipt, old-queue gate rejection, generation authorization consumption, content-only path resolution, and project-local output regression coverage. Tests: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_phase3_preflight_archive.py -q` → 48 passed, 1 skipped, 12 subtests passed; later combined gate suite remained green.

Task 3: complete — final release gate, strict pre-delivery human-review blocking, unified delivery fingerprint, unknown profile blocking, checklist exit code, and documentation. Tests: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_phase3_preflight_archive.py tests/test_review_checklist.py tests/test_release_gate.py tests/test_skill_guidance.py -q` → 89 passed, 1 skipped, 218 subtests passed.

Task 4: complete — local installed Skill synchronized and all nine modified/added runtime files hash-matched; compileall and git diff --check passed. Windmill isolated-copy smoke: strict preflight passed, queue stored production receipt, unauthorized claim was rejected, authorized claim succeeded. Full suite: 476 passed, 14 failed, 2 skipped, 431 subtests; the 14 failures are pre-existing asset-bundle/package baseline failures outside this workflow change.

Ruling: retain `standalone-legacy` queue mode when no `project.json` is discoverable — existing low-level queue fixtures and historical callers lack the project contract; making them synthesize a production receipt would expand scope and hide the distinction. Cost if wrong: a caller using the standalone API can bypass project gates, so production documentation and project-root detection must remain explicit.

Ruling: make missing `review.json` and missing final user approval blockers for `pre_delivery`/release — a release state without an auditable approval record is not a valid terminal state. Cost if wrong: legacy delivery-only projects must use the explicit delivery path or add the existing review record.

Self-review: found and fixed a receipt-binding gap. Production claim now verifies project root, book/version, plan fingerprint, workflow-rules version, and equality of the stored preflight receipt fields; tampered receipt regression passes.

Final verification: targeted workflow suite `90 passed, 1 skipped, 218 subtests`; full suite `477 passed, 14 failed, 2 skipped, 431 subtests`. The 14 failures remain the known asset-bundle/package baseline failures outside this change. Local Skill hashes match the worktree; isolated Windmill smoke passed with unauthorized claim rejected and authorized claim accepted.

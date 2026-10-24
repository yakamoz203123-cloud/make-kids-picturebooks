# SDD ledger — plan: docs/superpowers/plans/2026-10-24-core-optional-package-split.md

Pre-flight: reused the isolated worktree `chore/phase1-flow-reduction`; the phase is limited to release-package boundaries.

Task 1: complete — added RED tests for optional asset exclusion in the runtime package and project exclusion in the complete bundle.

Task 2: complete — made `projects/` a global packaging exclusion and added runtime-only exclusions for `core-v1.3`, STYLE-06, print assets, optional print/social/legacy scripts and references, plus full dependency manifests.

Task 3: complete — added `requirements-core.txt` and `requirements-optional.txt`, regenerated the checked-in runtime manifest, and documented the core/complete package distinction.

Verification: 14 package tests, 31 guidance tests, 7 release-guard tests, the full 431-test suite (2 skipped), `pip check`, `compileall`, `git diff --check`, and a core-package `workflow.py --help` smoke test pass. Final core ZIP: 2,409,327 bytes, 74 entries, zero projects and zero optional scripts/assets; complete bundle: 26,091,656 bytes, 229 entries, zero projects and all optional modules retained.

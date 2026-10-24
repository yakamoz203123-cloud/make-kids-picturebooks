# SDD ledger — plan: docs/superpowers/plans/2026-10-24-windmill-project-contract-migration.md

Pre-flight: the project data and the Skill validators are separate components; the project manifest consumes existing Research, whitelist, and trace files, while strict preflight consumes the manifest declarations. The fix must change only project metadata.

Ruling: keep `science_visual_consistency.status` as `pending` during pre-generation migration — marking it `passed` without a fresh human/visual review would turn a contract repair into fabricated evidence.

Ruling: retain the historical top-level `page-manifest.json` as a compatibility mirror, but synchronize it byte-for-byte with `content/page-manifest.json`; deleting or moving it would be a larger migration and is not required because the resolver accepts identical duplicates. `content/` remains the active source of truth.

Task 1: complete — baseline showed packet/story passed, manifest blocked on `missing_storyboard_science_review`, and strict preflight blocked on `research_references_undeclared`; the local contract check failed on missing `project_profile`.

Task 2: complete — updated the project profile, Research references, manifest-level science consistency metadata, and synchronized the historical top-level manifest mirror. `content_gate` packet/story/manifest and strict preflight all passed; science consistency remains `pending`.

Task 3: complete — production queue initialized with 9 pages in production mode, one explicit authorization was recorded, and page 1 was claimed as `running`. Non-target Research/story/layout/review hashes are unchanged; no image model calls or project writes came from preflight.

Final review: self-review (no subagent tool available) — the migration matches the plan, changes only project metadata, keeps the historical mirror synchronized, preserves non-target hashes, and leaves the two approval warnings plus science review as explicit follow-up conditions.

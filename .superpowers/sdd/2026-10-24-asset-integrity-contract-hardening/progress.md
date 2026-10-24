# SDD ledger — plan: docs/superpowers/plans/2026-10-24-asset-integrity-contract-hardening.md

Pre-flight: Task 1 produces the shared asset hash semantics consumed by release receipt validation; Task 3 consumes the existing style registry and does not depend on Task 2; Task 4 only changes the CLI boundary and preserves direct API compatibility.

Ruling: keep `STYLE-CORE-01:v1.2` as the default because `assets/style-registry.json`, templates, and `style_master.json` explicitly declare it; v1.3 is a released explicit alternative for STYLE-06. Promoting v1.3 globally would change the default contract and increase scope.

Task 1: complete — added shared canonical text hashing with raw legacy receipt compatibility; asset resolver, style lock, and character-bundle release validation use the shared semantics. Tests: `python -X utf8 -m pytest tests/test_asset_hashing.py tests/test_asset_production_real_assets.py tests/test_phase4_sample_gate.py tests/test_release_character_bundle.py -q` → 46 passed.

Task 2: complete — package identity now comes from the stable skill name and text entries are LF-normalized before archive hashing/writing. Tests: `python -X utf8 -m pytest tests/test_asset_phase1.py::Phase1AssetTests::test_skill_package_contains_phase1_registries_and_generated_manifest_once tests/test_skill_package.py -q` → 7 passed.

Task 3: complete — v1.2 remains the default; the repository v1.3 bundle is explicitly released, while the external staged project fixture remains pending and is tested as such. Added the version routing rule and the 80/20 asset guidance to the main Skill entry. Tests: `python -X utf8 -m pytest tests/test_phase2e_asset_versioning.py tests/test_character_assets_v12.py -q` → 13 passed, 115 subtests passed.

Task 4: complete — CLI queue initialization now rejects missing project contracts unless `--standalone-legacy` is explicit; direct Python API compatibility remains opt-in by its existing default for legacy fixtures. Tests: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_phase3_preflight_archive.py tests/test_skill_guidance.py -q` → targeted CLI test plus queue/contract suite: 48 passed, 1 skipped, 127 subtests passed.

Task 5: complete — full suite passed (`497 passed, 2 skipped, 431 subtests`, 228.06s); compileall and diff check passed; installed Skill runtime files were synchronized and hash-verified. Five-run installed smoke averages: strict preflight 692.6ms, queue init 846.2ms, authorization 309.1ms, authorized claim 286.1ms. No image model calls were added. Deferred: migrate direct Python API callers before changing its legacy default; repair the separate windmill project’s duplicate content layout and undeclared research/science review metadata without modifying that original project in this task.

# Task 6 baseline evidence

`baseline.jsonl` records the accepted 34-case pre-change observation set. `baseline-manifest.json` is the durable 34-record transcript manifest; `baseline-manifest.sha256` protects its exact bytes.

## Execution provenance

- Runner: desktop-bundled Codex CLI 0.149.0-alpha.4.
- Model: `gpt-5.6-luna`.
- Sandbox: `read-only`.
- Protected `SKILL.md` SHA-256: `4C02275C632864227BA463CBD71A4352C21075025F09413193B48512D7FD97F2`.
- Protected `agents/openai.yaml` SHA-256: `14A69FDE26261BB7938DEC7803D76ECD80A7FBEEE352B458AE5D0DB152C40BD8`.
- Evidence characteristics: 34 IDs/records/transcript directories, 25 successful staged-skill reads matching `triggered=true`, and no helper/setup errors.

## Observed result and limitation

The unchanged validator reports exactly two observed case failures: `negative_02` and `pressure_print_01`. The bundled CLI ignored `agents/openai.yaml` because `policy.products` includes unsupported `api`; this baseline therefore demonstrates `SKILL.md` behavior, not metadata-dependent behavior.

The raw transcripts and runner material are diagnostic-only and deliberately uncommitted at `.superpowers/task-6-baseline-app-v0149/` (about 338 MB). Their per-case output hashes are preserved in the committed manifest.

# 资产完整性与契约加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复跨平台资产回执、技能包身份、版本契约和 standalone CLI 绕过问题，同时保持 v1.2 默认生产行为。

**Architecture:** 新增一个共享的资产文件哈希模块，发布和验证使用同一规范；保留现有 `style-registry.json` 作为版本事实源，不新增第二套版本注册表；包和队列只在边界层增加显式身份校验。

**Tech Stack:** Python 3、JSON、pytest/unittest、现有 SHA-256 回执和 argparse CLI。

**Spec:** `docs/superpowers/specs/2026-10-24-asset-integrity-contract-hardening-design.md`

## Global Constraints

- `STYLE-CORE-01:v1.2` 仍是默认生产资产；v1.3 仅作为已发布的显式替代。
- 文本资产采用 UTF-8/LF 规范化哈希；二进制资产保持原始字节哈希。
- 不修改图片、故事、人工审核状态或真实项目资料。
- 正常生产路径不增加图片模型调用和并发。
- 无 `project.json` 的 CLI 队列必须显式传入 `--standalone-legacy`。

## Review Focus

- CRLF 文本回执在 Windows 上应通过，二进制字节变化仍应失败：Task 1。
- 新发布的 staged/formal receipt 必须与验证器使用同一哈希语义：Task 1。
- 从任意 worktree 路径打包时顶层目录仍是技能名：Task 2。
- v1.2 默认、v1.3 显式替代的文档和测试必须一致：Task 3。
- 缺失项目契约的 CLI 队列不能静默进入生产模式：Task 4。

---

### Task 1: 统一跨平台资产文件哈希

**Files:**
- Create: `scripts/asset_hashing.py`
- Modify: `scripts/asset_resolver.py`
- Modify: `scripts/release_character_bundle.py`
- Test: `tests/test_asset_hashing.py`
- Modify: `tests/test_release_character_bundle.py`

**Interfaces:**
- Produces `file_hash(path: str | Path) -> str` with text normalization and binary preservation.

- [x] **Step 1: Write failing tests**
  - LF 与 CRLF 的 JSON/Markdown 内容得到相同哈希。
  - 相同路径的二进制内容发生一个字节变化时哈希不同。
  - 现有正式 v1.2/v1.3 回执在当前 Windows checkout 下通过文件哈希层。

- [x] **Step 2: Run RED**

Run: `python -X utf8 -m pytest tests/test_asset_hashing.py tests/test_asset_production_real_assets.py tests/test_phase4_sample_gate.py -q`

Expected: 新测试失败；现有资产解析继续出现 `ASSET_MANIFEST_NOT_APPROVED`。

- [x] **Step 3: Implement shared hash**

Add text suffix handling in `asset_hashing.py`; import it from both production receipt writer and validators. Do not normalize images or other binary files.

- [x] **Step 4: Run GREEN**

Run: `python -X utf8 -m pytest tests/test_asset_hashing.py tests/test_asset_production_real_assets.py tests/test_phase4_sample_gate.py tests/test_release_character_bundle.py -q`

- [x] **Step 5: Commit**

`git commit -m "fix: make asset receipts cross-platform"`

### Task 2: 固定技能包身份

**Files:**
- Modify: `scripts/package_skill.py`
- Modify: `tests/test_asset_phase1.py`

**Interfaces:**
- `package_skill()` and `package_download_bundle()` use the `name` in `SKILL.md` front matter as archive top-level directory.

- [ ] **Step 1: Run the existing failing package test**

Run: `python -X utf8 -m pytest tests/test_asset_phase1.py::Phase1AssetTests::test_skill_package_contains_phase1_registries_and_generated_manifest_once -q`

Expected: fail because the worktree folder is `phase1-flow-reduction`.

- [ ] **Step 2: Implement stable package name**

Parse the required front matter `name`; reject unsafe or missing names instead of using the parent folder name.

- [ ] **Step 3: Run GREEN**

Run: `python -X utf8 -m pytest tests/test_asset_phase1.py::Phase1AssetTests::test_skill_package_contains_phase1_registries_and_generated_manifest_once tests/test_skill_package.py -q`

- [ ] **Step 4: Commit**

`git commit -m "fix: stabilize skill package identity"`

### Task 3: 对齐资产版本事实源

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `tests/test_phase2e_asset_versioning.py`
- Modify: `tests/test_character_assets_v12.py` only if the current assertion is still stale after documentation update.

**Interfaces:**
- Documentation and tests express the existing registry contract: v1.2 is default, v1.3 is released only when explicitly selected by a compatible style/page.

- [ ] **Step 1: Write/update failing contract assertions**
  - v1.2 remains default.
  - v1.3 manifest status is `released` and `production_enabled` is `true`.
  - documentation names both the default and explicit alternative.

- [ ] **Step 2: Run RED**

Run: `python -X utf8 -m pytest tests/test_phase2e_asset_versioning.py::Phase2EAssetVersioningTests::test_v12_is_still_the_default_and_v13_is_not_production_enabled tests/test_character_assets_v12.py::CharacterAssetV12Tests::test_skill_and_readme_route_to_the_bundle -q`

Expected: fail on the stale v1.3 state and missing explicit version documentation.

- [ ] **Step 3: Update only the stale contract assertions and guidance**

Do not change default resolver behavior or promote v1.3 globally.

- [ ] **Step 4: Run GREEN**

Run: `python -X utf8 -m pytest tests/test_phase2e_asset_versioning.py tests/test_character_assets_v12.py -q`

- [ ] **Step 5: Commit**

`git commit -m "docs: align asset version contract"`

### Task 4: 收紧 standalone CLI 入口

**Files:**
- Modify: `scripts/generation_queue.py`
- Modify: `tests/test_generation_queue.py`
- Modify: `SKILL.md`
- Modify: `README.md`

**Interfaces:**
- CLI `init` accepts `--standalone-legacy`; a missing project contract without that flag returns a clear non-zero error. Existing low-level Python API compatibility remains unchanged in this phase.

- [ ] **Step 1: Write failing CLI test**
  - A valid no-project fixture is rejected by CLI init without the flag.
  - The same fixture succeeds with `--standalone-legacy`.

- [ ] **Step 2: Run RED**

Run: `python -X utf8 -m pytest tests/test_generation_queue.py -q`

Expected: the new CLI boundary assertion fails before the flag exists.

- [ ] **Step 3: Implement CLI-only explicit legacy switch**

Pass an explicit internal allowance from the CLI to `init_queue`; retain direct API behavior so historical unit fixtures do not require broad rewrites.

- [ ] **Step 4: Run GREEN**

Run: `python -X utf8 -m pytest tests/test_generation_queue.py tests/test_phase3_preflight_archive.py tests/test_skill_guidance.py -q`

- [ ] **Step 5: Commit**

`git commit -m "fix: make standalone queue mode explicit"`

### Task 5: Final verification and efficiency measurement

**Files:**
- Modify: `docs/superpowers/.../progress.md` (git-ignored ledger only)

- [ ] **Step 1: Run focused suite, full suite, compileall and diff check**
- [ ] **Step 2: Run installed Skill Windmill smoke test**
- [ ] **Step 3: Measure preflight, queue init, authorization and claim timings**
- [ ] **Step 4: Perform final self-review and record deferred issues**

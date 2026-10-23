# 第一阶段流程精简 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 精简 `make-kids-picturebooks` 的默认生产流程，消除重复说明和重复全书检查，同时保留现有数据格式、脚本和历史兼容分支。

**Architecture:** 采用“主 Skill 负责路由、生产流程 reference 负责唯一详细流程、其他 reference 按条件加载”的结构。第一阶段只重构文档契约和指导测试，不引入新状态机或合并 schema。

**Tech Stack:** Markdown、Python `unittest`、现有 Skill 打包校验。

**Spec:** `docs/superpowers/specs/2026-10-24-phase1-flow-reduction-design.md`

## Global Constraints

- 默认输出继续是 `pure-images`。
- 默认生图继续一次一页、串行推进。
- 保留 `schema_version: 1` 和旧脚本。
- 不把技术生成成功写成视觉或发布批准。
- 私有儿童资料、角色照片和用户项目不进入公开 Skill 包。
- 本阶段不推送 GitHub。

## Review Focus

- 默认路径是否仍误触发 PDF/打印/社媒分支；由流程契约测试覆盖。
- 续做项目是否仍要求重复整本研究和全量审计；由续做规则测试覆盖。
- 队列是否被误写成内容门禁；由现有队列文档测试覆盖。
- 单页变化是否被错误扩大为全书失效；由失效规则测试覆盖。
- 质量门是否因精简而消失；由现有证据和验收测试覆盖。

---

### Task 1: 建立精简流程契约测试

**Files:**
- Modify: `tests/test_skill_guidance.py`

**Interfaces:**
- Consumes: `SKILL.md`、`references/production-workflow.md`、`README.md`、`RELEASE.md`。
- Produces: 能识别默认流程、续做流程、按需分支和不变量的结构测试。

- [ ] 写测试：要求文档包含目标流程顺序、续做最小读取集、整本失效条件和按需分支标记。
- [ ] 运行测试并确认旧文档失败。

### Task 2: 重构主入口和默认生产 reference

**Files:**
- Modify: `SKILL.md`
- Modify: `references/production-workflow.md`

**Interfaces:**
- Consumes: Task 1 的流程契约。
- Produces: 单一默认流程、清晰的模块职责和显式分支路由。

- [ ] 用最小文案满足失败测试。
- [ ] 保留所有安全、隐私、连续性、串行和证据不变量。
- [ ] 明确整本门禁、页面检查、队列和最终验收的边界。

### Task 3: 同步用户可见发布说明

**Files:**
- Modify: `README.md`
- Modify: `RELEASE.md`

**Interfaces:**
- Consumes: Task 2 的默认/可选/历史边界。
- Produces: 与主 Skill 一致的快速入口和发布范围。

- [ ] 更新默认生产流程说明。
- [ ] 保留版本、兼容能力和已知范围。

### Task 4: 验证并同步本地安装目录

**Files:**
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/SKILL.md`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/references/production-workflow.md`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/README.md`
- Modify: `C:/Users/Windows/.codex/skills/make-kids-picturebooks/RELEASE.md`

**Interfaces:**
- Consumes: Task 1–3 的已验证文档。
- Produces: 当前 Codex 实际加载的本地 Skill 与隔离分支一致。

- [ ] 运行聚焦测试、编译检查、Skill 包校验和 Git diff 检查。
- [ ] 将相同补丁应用到本地安装目录。
- [ ] 比较隔离分支与本地安装目录文件哈希。

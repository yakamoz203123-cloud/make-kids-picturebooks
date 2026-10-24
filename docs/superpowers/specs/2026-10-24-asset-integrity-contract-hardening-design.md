# 资产完整性与契约加固设计

日期：2026-10-24

## 意图

修复当前工作流之外、但会阻断真实生产的资产发布层问题：Windows `CRLF` 检出导致已批准资产回执失效、技能包顶层目录依赖 worktree 名称，以及 v1.2/v1.3 测试与发布状态漂移。

## 第一性原理

生产资产必须同时满足三件事：

1. 同一份文本资产在不同操作系统上得到同一个完整性结论。
2. 资产版本的默认/替代关系只有一个事实源。
3. 包和队列的身份不能由临时目录名称或隐式兼容分支决定。

## 目标

- JSON/Markdown 等 UTF-8 文本资产采用稳定的 LF 规范化哈希；PNG 等二进制资产保持原始字节哈希。
- 复用现有 `assets/style-registry.json` 作为版本事实源：`STYLE-CORE-01:v1.2` 仍是默认，已发布的 v1.3 只作为显式生产替代。
- 技能包顶层目录使用 `SKILL.md` 的稳定技能名 `make-kids-picturebooks`。
- CLI 创建没有 `project.json` 的 standalone 队列时必须显式声明兼容模式。

## 非目标

- 不修改图片内容、角色外观、故事文本或人工审核结论。
- 不把 v1.3 强行改成全局默认。
- 不移除底层 Python API 的历史兼容能力；本阶段先收紧用户可执行 CLI 入口。
- 不增加图片模型调用或并发。

## 方案比较

### 方案 A：规范化文本哈希 + 现有 registry + CLI 显式兼容（采用）

在单一哈希模块中统一发布和验证逻辑；从现有 style registry 读取默认/替代关系；包名来自技能元数据；CLI 对 standalone 兼容显式要求参数。

优点是改动小、保持已有 v1.2 默认行为、修复 Windows/CI 差异，并把风险集中在边界层。代价是旧回执的哈希语义需要明确为“文本内容规范化哈希”。

### 方案 B：每个平台重新生成资产回执

让 Windows 和 Linux 各自生成不同回执。它会掩盖跨平台问题，回执不可移植，发布包在另一台机器仍可能失效，放弃。

### 方案 C：关闭资产回执校验

可以让测试变绿，但会删除生产资产的不可变性证明，违反 fail-closed 约束，放弃。

## 关键接口

- `scripts/asset_hashing.py`：提供 `file_hash(path)`；文本按 UTF-8 + LF 规范化，其他文件按原始字节。
- `scripts/asset_resolver.py` 和 `scripts/release_character_bundle.py` 共享该函数，禁止各自实现哈希。
- `scripts/package_skill.py` 从 `SKILL.md` front matter 读取包名。
- `generation_queue.py` CLI 增加 `init --standalone-legacy`，没有项目契约时默认阻断。

## 效率边界

哈希规范化只发生在资产发布/验证边界，不发生在逐页生图调用；文本文件通常是 KB 级，PNG 仍只读一次原始字节。包名解析只发生在打包开始时。standalone 参数只改变错误路径，不增加正常生产路径的调用次数。

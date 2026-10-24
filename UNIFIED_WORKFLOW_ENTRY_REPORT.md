# 统一生产入口优化报告

日期：2026-10-24
范围：`make-kids-picturebooks` Skill 第一阶段流程精简的统一入口改造

## 结论

本阶段已把日常生产从多个底层接头压缩为三个用户动作：

1. `doctor`：检查项目现在能不能继续；
2. `resume`：安全地初始化/复用队列，并最多推进一页；
3. `deliver`：进入现有最终交付门禁。

这不是重写流程，也没有增加新的审批系统。新入口只是薄编排层，底层的知识、内容、资产、路径、连续性、授权、生命周期和人工审核规则仍由原模块负责。

## 第一性原理判断

用户不需要记住十几个内部脚本，只需要得到三个决策结果：

| 用户问题 | 统一动作 | 结果 |
|---|---|---|
| 项目能不能生产 | `doctor` | `passed` 或带阻断项的 `blocked` |
| 下一步能不能推进 | `resume` | `authorization_required`、`waiting`、`claimed`、`complete` 或 `blocked` |
| 能不能正式发布 | `deliver` | 复用既有 `pre_delivery/strict` 和发布回执规则 |

## 新增功能

文件：`scripts/workflow.py`

### `doctor`

- 默认调用现有 `pre_generation/strict`；
- 只读，不创建队列、不授权、不调用图片模型；
- 返回页数、阻断项、警告、计划指纹、写操作数和下一步建议；
- 详细证据仍通过原 `project_preflight.py` 获取。

### `resume`

- 默认队列位置为 `books/<book-key>/<version>/review/production-queue.json`；
- 强制统一入口使用 `max_in_flight=1`，保持单页串行；
- 复用现有队列和有效预检回执；
- 没有明确授权时返回 `authorization_required`，不会自动批准；
- 有授权时只消费一次有限授权、只领取一页；
- 页面已在运行时返回 `waiting`，不会擅自把运行状态解释为中断；
- 对失败页、未知请求和其他人工介入状态停止，不自动重试或恢复。

### `deliver`

- 直接委托 `release_pure_image_delivery.release_delivery`；
- 不复制发布判定；
- 保留交付验证、`pre_delivery/strict`、人工审核和唯一 `release-receipt.json` 规则。

## 效率影响

### 对人的效率

日常路径从“记住并按顺序调用多个内部脚本”变成“做三个决策动作”。这减少了漏掉授权、顺序错误和把技术成功误认为发布成功的概率。

### 对机器的效率

- 不增加图片模型调用；
- 不提高并发，统一入口固定单页串行；
- 不引入新的全书扫描或重复校验逻辑；
- `resume` 继续使用已有的预检回执、计划和页面授权复用机制；
- `doctor` 是可选诊断动作。正常推进可以直接使用 `resume`，避免先 `doctor` 再 `resume` 造成不必要的诊断重复。

因此，本次改造不会让生产链变得更繁琐，也不会以牺牲门禁换取速度；它主要压缩的是用户操作复杂度。

## 安全边界

- 不改变 `schema_version: 1`；
- 不绕过 Research、内容、资产、路径、连续性或人工审核；
- 不自动批准生成；
- 不自动恢复 `pending_unknown`；
- 不自动重试耗尽或失败页面；
- 不删除底层命令，诊断和历史兼容仍可直接调用；
- 技术生成成功仍不等于视觉审核通过或最终发布批准。

## 验证结果

以下结果均在隔离分支 `chore/phase1-flow-reduction` 中取得：

- 统一入口专项测试：`7 passed`；
- 入口、效率、队列、生命周期、发布门禁和指导测试：`98 passed, 1 skipped, 218 subtests passed`；
- 完整测试集：`516 passed, 2 skipped, 441 subtests passed in 211.08s`；
- `python -X utf8 -m compileall scripts`：通过；
- `git diff --check`：通过；
- 临时 Skill 打包：版本 `0.11.0-preview`，ZIP 成功生成；
- 合成故事“ 小熊看见一颗种子 ”验证了：无授权不领取、有授权领取一页、运行中等待、已有缓存返回完成、交付动作委托既有发布函数。

## 用户日常使用

```bash
python scripts/workflow.py doctor /absolute/project b01 --version v1
python scripts/workflow.py resume /absolute/project b01 --version v1
python scripts/workflow.py resume /absolute/project b01 --version v1 --approval "用户批准继续生成下一页" --max-calls 1
python scripts/workflow.py deliver /absolute/project b01 /absolute/project/books/b01/v1/delivery/pure-image-delivery-v1 --version v1
```

其中 `doctor` 只在需要检查项目时使用；普通续做可直接从 `resume` 开始。

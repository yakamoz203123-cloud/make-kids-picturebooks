# 核心角色资产包 v1.2

这是 `make-kids-picturebooks` 的可复用卡通角色资产包。唯一视觉基准是 `reference/core-character-assets-v1.2.png`；本包不重新设计小熊、小猛或妈妈，也不包含原始儿童照片。

## 角色 ID

| character_id | 角色 | 角色定位 | 默认服装 |
|---|---|---|---|
| `xiaoxiong` | 小熊 | 3—4岁女孩主角 | `G-01` |
| `xiaomeng` | 小猛 | 3—4岁男孩主角 | `B-01` |
| `mother` | 妈妈 | 成人辅助角色 | `M-01` |

固定身份资产分别是 `G-ID-01`、`B-ID-01`、`M-ID-01`。脸型、五官比例、发型、发色、肤色、身体比例、年龄感和角色气质必须以总览图为准。

## 资产目录

```text
core-v1.2/
├─ reference/core-character-assets-v1.2.png
├─ characters/
│  ├─ xiaoxiong/{identity,expressions,poses,angles,outfits}/
│  ├─ xiaomeng/{identity,expressions,poses,angles,outfits}/
│  └─ mother/{identity,expressions,poses,angles,outfits}/
├─ shared/{interactions,style}/
├─ manifest.json
└─ README.md
```

目录内的分类说明文件是调用入口；所有机器可读记录以 `manifest.json` 为准。

## ID 范围

- 小熊服装：`G-01`—`G-08`；小猛服装：`B-01`—`B-08`；妈妈服装：`M-01`—`M-06`。
- 小熊表情：`G-EX-01`—`G-EX-12`；小猛表情：`B-EX-01`—`B-EX-12`；妈妈表情：`M-EX-01`—`M-EX-08`。
- 小熊动作：`G-PO-01`—`G-PO-12`；小猛动作：`B-PO-01`—`B-PO-12`；妈妈动作：`M-PO-01`—`M-PO-10`。
- 角度：`ANG-01`—`ANG-08`，适用于三位角色。
- 双人互动：`DUO-01`—`DUO-08`；亲子互动：`PARENT-01`—`PARENT-07`。
- 统一画风：`STYLE-CORE-01`。

## 后续绘本调用方式

每一页先绑定固定资产，再填写页面变化：

```yaml
character_asset_bundle: core-characters-v1.2
character_asset_version: v1.2
characters:
  - character_id: xiaoxiong
    outfit_id: G-01
    expression_id: G-EX-02
    pose_id: G-PO-03
    angle_id: ANG-02
  - character_id: xiaomeng
    outfit_id: B-01
    expression_id: B-EX-05
    pose_id: B-PO-01
    angle_id: ANG-03
interaction_id: DUO-03
style_asset_id: STYLE-CORE-01
page_delta:
  scene: "厨房窗边的小桌"
  prop: "两只大小不同的杯子"
  knowledge_evidence: "孩子能看见两个杯子的高度差"
  continuity: "承接上一页两人发现杯子不同"
```

生产提示词只描述选中的资产 ID和 `page_delta`。不要每页重新发明人物，也不要把整张设定总览图当作默认正式画面输入；正式生成应使用干净的单角色或互动参考。

## 生产规则

1. 约 **80% 固定资产**：角色身份、比例、画风、服装、表情、动作、角度和互动关系。
2. 约 **20% 页面变化**：场景、道具、知识证据、构图、文字安全区和页间连续性。
3. 一页只能使用本包中已登记且兼容的角色／资产 ID。
4. 角色资产包版本必须写入逐页清单；修改视觉身份时建立新版本，不覆盖 v1.2。
5. 角色设定页只用于核对身份。它不是成品画面，也不是每页必须重复提交的长提示词。

## 机器读取

```python
import json
from pathlib import Path

bundle = Path("assets/characters/core-v1.2")
manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
asset = next(a for a in manifest["assets"] if a["asset_id"] == "G-PO-03")
```

当前资产包是 Skill 内的卡通参考资源；它不会自动替代项目中已批准的私有真实儿童角色。若一个项目明确选择本包，应在项目角色记录中写明 `character_asset_bundle: core-characters-v1.2`。

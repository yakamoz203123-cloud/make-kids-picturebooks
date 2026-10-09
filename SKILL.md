---
name: make-kids-picturebooks
description: Use when the user provides an adult knowledge book or chapter and wants original illustrated picturebooks for a selected age band (3–4, 5–7, or 8–10), age-appropriate topic selection from books, chapter-limited adaptation, home-printable booklets, or continuation and revision of an existing children's knowledge-picturebook project. Also use for economics, mathematics, physics, chemistry and engineering book-to-picturebook requests.
---

# 宝宝知识绘本

从成人知识书中筛选适合所选年龄的概念，转成孩子能跟随的原创故事与画面。章节用于定位来源，制作顺序按儿童的理解和铺垫需要安排。默认交付一份含真实插画、可直接家庭打印的绘本PDF（便携式文档格式），保存可续做进度。支持选择3—4岁、5—7岁或8—10岁，每次只制作所选年龄段，跨书沿用固定虚构儿童伙伴。

## 开始与范围

1. 读取本次来源和已有项目，不依赖对话记忆补全书籍或进度。查找同名项目时使用文件保存环境的检索能力。
2. 区分“筛选选题”“单册试做”“已选主题批量制作”“继续”“修改某页”。默认先阅读 [适龄选题筛选](references/topic-selection.md)，提出少量有来源依据的适龄主题及取舍理由；未指定制作范围时只将优先推荐的一册放入本次队列并完成。用户指定某章时在该范围内筛选；用户明确要求按章推进时保存 chapter_order（按章模式），仍允许不适龄内容零册。批量范围已明确时按所选主题队列完成，不逐册请求确认。
   阅读 [年龄选择与分层](references/age-bands.md)。先确定本次目标年龄：用户明确指定时直接采用；继续项目时沿用当前册或项目已选单一档位；新项目未指定或范围跨档时，只询问一次年龄选择，等待回答后再创作正文和插画，期间可读取来源。只评估并制作所选档位，本次明确要求多个年龄版本时才做多套。按所选年龄与已选概念评估所需册数；一个主题可以一册或多册，主题册数与年龄版本数分开。保存目标年龄，不将同一套正文标为适合所有年龄。
3. 检查文本读取、图像生成、中文可嵌入字体、排版及渲染能力。缺失能力时报告阻碍并保存成果，不改用插画提示冒充完整绘本。
4. 新项目复制 [项目模板](assets/project-template.json)。用独立项目保存来源、章节评估、概念卡、角色参考、分镜、插画、版面数据及成果。生成文件使用可用的持久文件保存流程；技能资源只读，不在技能目录保存用户书籍或人物资料。

## 执行流程

1. 阅读 [改编规则](references/adaptation.md)。建立覆盖范围明确的书籍地图，先查看目录与相关片段、再实际读取候选概念的上下文，按所选年龄筛选、去重与排序。保存来源位置、儿童目标、适龄理由、必要铺垫、取舍状态及所需册数。可跨章节组合解释同一核心概念；难以安全、准确地故事化的内容暂缓或跳过。只有实际核验的主题进入制作队列；不为覆盖全书安排册数。
2. 为每册保存概念卡、完整朗读故事和逐页分镜。正文要让家长直接逐页读完，包含愿望、问题、行动、转场和情感结尾；先通读检查故事，再分配页面；逐页分镜记录叙事用途并做删除／合并检查，按自然节奏选择合适的4倍数页数，不能用短句图片说明冒充完整故事。保留来源位置、关键条件、儿童目标、类比边界及独立家长说明；儿童绘本默认只含封面、故事和封底，来源、改编边界、共读建议与打印指导另存说明文件，仅在用户明确要求时附家长页；故事原创，每册一个核心概念，图像承载探索过程。概念卡记录故事事件为何体现概念、必须出现的视觉证据；逐页检查实际证据，不为迁就错误图片改掉概念成立条件。
3. 阅读 [角色规则](references/characters.md)。复用已确认角色参考；首次由用户确认角色设定和标准图。用户授权临时角色测试时单独标注，不默认为正式系列角色。
4. 阅读 [艺术指导与多画风](references/art-direction.md)，保存每册风格卡；首次探索或本次要求多风格时先做同场景三方向对照，既有认可方向直接复用。同册保持视觉语言一致，不同册可采用不同方向。先完成含真实正文的样页，再扩展全册。阅读 [图文构图规则](references/composition.md)和 [逐页记录](references/page-records.md)。先共同安排正文区域、人物动作、道具和阅读顺序，再使用可用图像生成技能或工具实际生成逐页插画；先看参考图，绑定人物、道具、动作与知识检查点。保存逐页道具数量、位置、状态、变化及当前素材路径。正文以可编辑文字在排版时放进画面的自然留白；插画生成时保留该区域，不输出独立矩形图片加正文块的故事页。按 [检查规则](references/review.md)逐页检查，问题页最多两轮针对性修订；仍有关键缺陷时保存阻碍。
5. 阅读 [打印规则](references/printing.md)，填写 [版面模板](assets/book-template.json)。按 [验收与导出](references/acceptance.md)使用通用导出脚本生成阅读版、已经拼好的打印版及全部页面预览，实际查看每个阅读页和打印面。
6. 保存含逐页证据的检查记录，用统一验收脚本核对素材、正文、版本、字体、PDF和审核文件，通过后生成文件摘要并更新项目状态。默认只向用户交付一份已拼好的家庭打印PDF（便携式文档格式），回复附简短打印指导；用户明确选择屏幕阅读时改交阅读版，明确要求两版时才同时交付。家长说明和制作资料保留在项目中，用户要求时再提供；保留可编辑数据、插画及概念卡；可用 package_project.py 打包本册通过验收的当前素材，文件属于用户私有项目，公开发布另行审查。没有实物反馈只记录数字检查通过。

## 脚本调用

将 `SKILL_DIR`（技能目录变量）设为当前实际技能目录，不能硬编码初始目录名；保存后目录可能变化。调用脚本使用解释器。

```bash
python3 "$SKILL_DIR/scripts/project_state.py" /absolute/project/project.json
python3 "$SKILL_DIR/scripts/validate_page_manifest.py" /absolute/project/books/b01/page-manifest.json --require-images
python3 "$SKILL_DIR/scripts/export_book.py" /absolute/project/books/b01/v1/layout.json /absolute/project/books/b01/v1/export
python3 "$SKILL_DIR/scripts/accept_book.py" /absolute/project/project.json b01
python3 "$SKILL_DIR/scripts/accept_book.py" /absolute/project/project.json b01 --accept /absolute/project/books/b01/v1/acceptance.json
python3 "$SKILL_DIR/scripts/package_project.py" /absolute/project/project.json b01 /absolute/project/output/b01-materials.zip
```

运行环境为Python 3.10及以上；依赖见 requirements.txt，包括 reportlab（文档排版库）、Pillow（图像处理库）、pypdf（文档处理库）、fontTools（字体检查库）和PyMuPDF（文档渲染库）。优先使用环境已有依赖，缺失时报告具体能力。图像生成与电子书读取由执行环境提供，并非这些脚本自带。默认使用附带的中文打印字体；可在版面文件指定其他支持中文且可嵌入的字体。附带字体、许可及固定上游来源见 assets/kidsbook-print.ttf、assets/font-license.txt 和 assets/font-provenance.json。项目验收前复制字体到项目并保存相对路径。不要降级成缺字输出。

进度状态依次为 assessed（已评估）、planned（已规划）、text（文字完成）、illustrated（插画完成）、laid_out（已排版）、digital_checked（数字检查通过）、print_checked（实物试打通过）。用状态脚本检查下一动作；来源或角色版本变化时先重新核验受影响册。保留旧版，在版本目录输出新成果。

完成前清单检查、逐页知识及视觉检查、清单与版面对应检查都通过。清单脚本只验证记录和指定文件是否存在，不替代科学判断或图像审核。旧项目缺少验收记录时先保留旧文件，将状态设为laid_out（已排版），补全单一目标年龄、页面类型、逐页审核与验收后再记录完成。验收文件摘要失效时先重新检查受影响册；不自动改写通过证据。

## 完成标准与常见问题

- 有分镜没有实际插画：仅文字阶段完成。
- 有文件未逐页视觉检查：仅已排版。
- 数字检查通过：可以交给家长试打，不表示实物已验收。
- 试打通过：仅在用户确认打印与装订正常并记录反馈后设置。
- 页面数量、结构和科学关系错误：修复对应画面，不用文字解释掩盖错误。
- 来源只有部分内容：只对实际读取的片段作适龄结论；目录线索标为待核验，不宣称已筛选完整本书。
- 总页数不足4倍数：先调整有叙事用途的分页，例如拆开请求与回应；可用有用途的扉页或封底，不用家长说明、机械总结或重复画面凑页数。
- 继续任务：核对实际文件、版本及本次主题队列，推进第一个已选未完成册；未选中或暂缓的内容不自动补做。用户要求再做一册时，从已核验适龄主题中挑选下一项并更新队列。本次队列完成只代表当前范围完成。

示例：“从这本书里挑适合5—7岁孩子的内容，给出选题和理由，先做最适合的一册，沿用已有儿童角色，生成家庭双面打印文件。”

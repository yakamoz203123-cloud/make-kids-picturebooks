# 制作检查

逐册保存检查记录：检查项、结果、具体页码、证据文件、待修问题、修订次数。缺陷未解决时不能标记数字检查通过。

## 四类证据必须分开

在 `review.json` 中分别保存以下四个 evidence（证据）域；一个域的通过不能替代其他域：

- **engineering evidence**：确定性脚本与文件检查，例如页数、尺寸、字体嵌入、可提取文字、有效图片、队列状态和导出摘要；
- **content evidence**：来源位置、教育目标卡、年龄适配、知识边界、故事因果和逐页知识证据；
- **visual evidence**：逐页 `layout_review`、`text_image_match`、`continuity_review`、相邻页成对审核和整书总览；
- **real-reading evidence**：实际家庭共读、试打或儿童反馈，记录日期、参与者、观察和后续修改；没有发生时明确写 `pending`。

每册还必须保存 `contact_sheet_review`：

```json
{
  "contact_sheet_review": {
    "status": "pending|passed|failed",
    "evidence": "实际查看整书缩略图总览后的观察",
    "image_path": "output/v1/contact-sheet.png",
    "reviewer": "human|model|human+model",
    "reviewed_at": "YYYY-MM-DDThh:mm:ss+08:00"
  }
}
```

contact sheet review 只用于整书层面的角色漂移、色彩节奏、景别重复、文字位置和叙事空页检查；它不能替代逐页视觉审核，也不能声称自动审美通过。脚本的 deterministic gates 只核对记录和文件，never automatic proof。

0. 教育目标：正式分镜前已完成并核对 `education-goal.json` 的 `core_knowledge`、`target_age_band`、`prior_experience`、`visible_relationship`、`knowledge_boundary` 和 `reading_observation`；目标卡不是儿童理解证据。
1. 年龄：明确所选3—4岁、5—7岁或8—10岁；只审核本次要求的年龄版本，核对行动、因果、比较和阅读问题符合所选创作策略，项目、册与清单年龄一致。旧册5—6岁保留原标记和适用范围。
2. 知识：来源可定位、关键条件保留、概念卡及故事因果一致、类比边界明确；记录故事事件为何体现概念及必须出现的视觉证据，并核对实际画面，不能只写“科学通过”。
   使用 Research 包时，先核对四文件门禁和 `knowledge-whitelist.json`；逐句科学断言必须能回溯到 allowed claim，`inference` 不得升级为 fact，`uncertain`、`pending_confirmation`、`omit` 不得进入儿童事实。逐页 `knowledge_claims` 与 `science_visual_checks` 必须和实际画面对应，并做 storyboard-level 的条件、顺序、数量和状态一致性检查。
3. 故事：通读整册确认家长无需临时补话也能讲完；正文不是图片标签。核对无页码的完整朗读稿：愿望明确、行动有因果、态度变化有可见触发、结尾回应开头；不能以“过了一会儿”或知识总结掩盖转场缺口。朗读顺畅、角色有愿望和行动、目标年龄的孩子可跟随情节、无硬加说教；8—10岁版同时支持自主阅读。
   分页：核对每页分镜的叙事用途，并实际做删除／合并检查，记录保留或调整的理由。安静观察和情绪停顿可以保留；对故事、节奏和观察均无贡献的页先改写、合并或删除。不能因总页数为4倍数、文字不溢出就判断该页通过。完成整本分镜后做相邻页重复审计，区分无价值的重复和服务于科学比较的有价值的重复。
4. 图像：固定人物一致，物体数量可数，结构及变化准确，前后道具连续；核对逐页数量、位置、状态、变化，清单所选图与版面实际图一致，正文版本与文字区域一致。做 adjacent-page pair 审核：每个相邻页对照前页 `next_page_hook` 与后页 `current_page_entry`、角色外观、`character_reference_path`、道具和情节状态，并在 `continuity_review` 写入实际证据。
   同时做 text-image state matching，在 `text_image_match` 写入正文与画面人物、动作、数量、位置、时间和知识条件的实际比对证据。
5. 版面：默认检查无字源图的自然文字安全区、视觉焦点、留白和关键对象遮挡，正文保持独立可编辑；不能每页固定上图下文。家长说明默认另存文件；未明确要求时，检查儿童绘本内没有制作说明或凑页数的总结。用户明确要求可阅读图文时，再渲染小红书 `1080×1440` 成品并查看缺字、溢出、遮挡、重叠、平台避让区和标点断行。压缩导出后再次核对文字层，不能仅凭画面可读就通过。用户明确要求历史打印分支时，另行渲染阅读页和打印面，检查字体嵌入、可提取文字、纸边和书脊，不把该分支证据当作默认无字交付或社媒成品证据。
   审美：按艺术指导核对风格卡与实际成页。整册角色、道具、材质和主色连续；视觉焦点清楚，表情可读，花草及纹理不抢正文和关键动作；远近景、安静与行动形成节奏。同场景多风格对照仅证明方向探索，不计为整册插画完成。
6. 技术：默认检查源图页面实际存在、可解码、尺寸为 `1080×1440`、源图为 `3:4`、交付副本与源图关系可追溯。明确要求可阅读图文时，再检查文字在安全区内且 `social-output.json` 与逐页产物一致；历史打印分支才检查字体嵌入、PDF 页数尺寸、有效图片分辨率、拼版每页恰好一次与折叠顺序。
7. 续做：核对实际成果是否存在，状态与成果一致；变更来源或角色先重新核验。
8. 实物：先一张纸测试方向，再整册折叠装订；用户反馈后才标记试打通过。

数字检查可在环境中完成；纸张、双面方向、颜色和宝宝试读必须基于真实反馈。不宣称已完成不可观察的环节。工程、内容、视觉和真实阅读 evidence 分开记录；脚本的 deterministic gates 检查记录和文件；visual identity、scene readability、science/story consistency 仍须 human/model visual review，never automatic proof。

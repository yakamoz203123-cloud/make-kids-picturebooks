# 验收与导出

## 制作记录

用户默认收到一份家庭打印成品；内部保留阅读顺序文件用于拼版和逐页审核，这些内部成果不等于需要向用户交付多个版本。

每册的 artifacts（成果路径）保存 concept、story、storyboard、layout、page_manifest、reading_pdf、print_pdf、review；完成后另外保存 acceptance（验收记录）。所有资产放入项目目录，路径相对于其记录文件；不依赖旧工作区、账号或机器字体目录。保存角色参考目录 characters_path。附带字体复制到项目时同时复制 font-license.txt 和 font-provenance.json，并在版面保存 font_license_path 和 font_provenance_path，以便验收和打包保留第三方许可；自定义字体保存其实际许可，不套用附带字体的许可。

版面每页填写 kind（页面类型）：cover（封面）、story（故事）、parents（家长说明）、back（封底）或blank（有意留白）。故事页必须有实际插画、background（背景）图像角色和已实际查看的文字留白确认。清单选图、版面选图及文字区域必须一致，正文与分镜逐字一致。逐页清单的知识检查应记录实际观察，不把生成提示当证据。

## 质量选择

默认 quality_profile 为print（打印），target_dpi 不低于300。用户明确选择家庭试制时设为home-pilot（家庭试制），target_dpi 不低于200，同时 quality_approval 保存该选择的原话或准确记录。没有用户选择记录不降档。阅读版正文与家长说明至少22磅；家庭打印版为留出纸边会同比例内缩，22磅阅读正文约为20.6磅打印文字。实物可读性需试打确认，不声称打印成品仍为22磅。分辨率按原生像素和实际放置尺寸检查，不插值放大冒充高清。

## 导出和审核

运行 export_book.py，输出到新的版本目录；包含阅读PDF、横向A4拼版PDF、每个阅读页和每个打印面的PNG及导出报告。图片压缩保持像素尺寸，文字保留为可提取文字。导出报告只表示导出完成，review_status（审核状态）仍为pending（待审）。实际检查每一页人物、数量、动作、知识条件、中文字、留白和拼版，不仅检查缩略图或抽样页。

在 review.json 保存 reading_pages 和 print_sides 数组，每项对应连续页码或面码：

```json
{"reading_pages":[{"page":1,"status":"passed","evidence":"实际观察的内容及检查结论","image_path":"output/v1/reading-pages/page-01.png"}],"print_sides":[{"side":1,"status":"passed","evidence":"实际观察的配对、方向、文字和边距","image_path":"output/v1/print-pages/page-01.png"}],"unresolved_digital_defects":[]}
```

上述仅展示单项结构，实际记录须覆盖全部页和面。家长说明没有插画时，清单 current_image_path 指向实际审核的渲染页，不能填空白替代文件。记录图像生成调用次数、修订次数及未解决问题；实物打印和共读反馈独立记录，未发生时明确待验证。

## 完成及续做

运行 accept_book.py 检查实际文件；所有检查通过后以 --accept 保存新验收记录，状态才设为digital_checked（数字检查通过）。验收记录包含源文件、角色参考、正文、分镜、当前插画、提示、版面、字体、PDF和审核证据的摘要。修改任一资产后重新导出和审核，用新版本验收，不修改旧摘要来绕过检查。脚本核对可检查的结构和文件，科学判断和图像审核由执行者负责。

运行 project_state.py 时检查验收摘要，文件缺失或变更返回revalidate（重新验收）。在selected_topics（适龄主题模式）下只推进本次已选册队列，队列结束不自动续做未读章节或未选候选项。新项目默认此模式；旧项目缺少模式时脚本保留旧行为，执行者先按本次用户要求保存模式和主题队列，保留旧作品。用户点名修改旧册时先将该册加入本次队列。按章模式须有明确范围依据。

# make-kids-picturebooks

宝宝知识绘本技能：把成人知识书或已核验的知识主题改编为适龄原创绘本生产工作包。

当前发布版本：`v0.11.0-preview`。

默认交付是 `pure-images`：逐页无字插画、独立可编辑正文和可追溯的审核记录。可阅读图文、PDF、打印拼版、社媒版式和 9:16 输出均需用户明确请求。

## 默认最短流程

```text
输入契约 → 知识门禁 → 故事/整本分镜 → 资产锁定
→ 一次整本 strict 预检 → 串行逐页生图
→ 页面审核 → 失败页局部返工 → pure-images 确定性交付
```

继续已有项目时只读取项目摘要、当前页任务/依赖、有效预检回执和当前页队列状态。研究、年龄档、故事、页数、关键角色/画风、连续性契约、输出模式或预检规则变化时才重新运行整本 strict；单页提示词或资产变化只返工当前页。

PDF、打印、社媒渲染、历史迁移、发布打包和完整性能统计属于按需或历史兼容分支，不会因脚本存在而自动进入默认流程。

## 本地验证

```text
python -X utf8 -m compileall scripts
python -X utf8 -m unittest discover -s tests -q
python -X utf8 -m pip check
python scripts/package_skill.py . ../dist/make-kids-picturebooks-v0.11.0-preview.zip --version 0.11.0-preview
```

CI 运行指导、发布门禁和技能打包的聚焦测试；完整测试集包含渲染和外部环境相关用例，需在具备对应工具的环境中单独运行。

仓库不包含用户书籍、儿童资料、私人角色照片或生成项目。发布包名为 `make-kids-picturebooks-v0.11.0-preview.zip`。

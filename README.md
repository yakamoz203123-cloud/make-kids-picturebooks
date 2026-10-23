# make-kids-picturebooks

宝宝知识绘本技能：把成人知识书或已核验的知识主题改编为适龄原创绘本生产工作包。

当前发布版本：`v0.11.0-preview`。

默认交付是 `pure-images`：逐页无字插画、独立可编辑正文和可追溯的审核记录。可阅读图文、PDF、打印拼版、社媒版式和 9:16 输出均需用户明确请求。

## 本地验证

```text
python -X utf8 -m compileall scripts
python -X utf8 -m unittest discover -s tests -q
python -X utf8 -m pip check
python scripts/package_skill.py . dist/make-kids-picturebooks-v0.11.0-preview.zip --version 0.11.0-preview
```

仓库不包含用户书籍、儿童资料、私人角色照片或生成项目。发布包名为 `make-kids-picturebooks-v0.11.0-preview.zip`。

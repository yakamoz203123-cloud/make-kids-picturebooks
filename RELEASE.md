# make kids picturebooks 0 9 1

## 发布范围

这是保留 `schema_version: 1` 兼容性的稳定化预览版本，包含以下改进：

- Windows 和 Linux 下的项目相对路径规范化；
- 来源文件和角色目录的显式资产边界；
- 字体文件、许可证和来源证明的验收要求；
- 故事页正文顺序核对，封面和封底不误判为朗读稿；
- UTF-8 测试夹具和当前 PyMuPDF 导入方式；
- 来源内容安全边界、年龄选择、角色确认和画风确认规则；
- 单顶层目录技能包与完整下载包的非覆盖式打包。

## 兼容性

- Python 3.10 及以上；
- 目标验证平台为 Windows 和 Linux；
- 依赖版本见 `requirements.txt`；
- 默认打印质量为 300 DPI 或更高，使用项目内附带的中文打印字体。

## 验证命令

```text
python -X utf8 -m compileall scripts
python -X utf8 -m unittest discover -s tests -q
python -X utf8 -m pip check
```

发布前还应在 Windows 和 Linux 上分别运行上述命令，并检查验收、续做、打包和重复执行不会覆盖已有输出。

## 已知范围

本版本不包含 Schema v2、多年龄独立队列、v1 到 v2 迁移工具和 3–4、5–7、8–10 岁三套真实样册。行为评测更新结果也不作为本版本的完成证据；这些内容属于 v1.0 发布门槛。

公开包只包含技能源码、测试、脚本、参考资料、模板、许可证和字体来源证明，不包含任何用户书籍、儿童资料、角色参考或生成项目。

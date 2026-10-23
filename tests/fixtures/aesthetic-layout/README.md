# Aesthetic layout fixture

这是一个最小端到端回归样例：4 页、4 张 9:16 合成插画底图，使用 `scene-integrated`、`soft-card` 和 `narrative-band` 三种 `layout_mode`，正文包含可提取的中文文字。

- `layout.json`：版面输入，文字与图像仍是技术分层。
- `rendered/reading.pdf`：阅读版 PDF；`rendered/print.pdf`：打印拼版 PDF。
- `rendered/reading-pages/`、`rendered/print-pages/`：供人工逐页查看的打印/阅读渲染图。
- `social/`：4 张独立的 `1080×1920`、`social-vertical-9x16` 社媒竖屏 PNG；这是显式旧 profile 的兼容回归样例，不代表当前小红书默认值。当前小红书默认输出为 `xiaohongshu-feed-3x4`、`1080×1440`。

插画是测试用合成素材，不是成品素材。这里的输出用于验证渲染、文字提取、尺寸、清单和安全区；它们不构成自动审美通过证明，也不替代逐页人工或模型视觉审核。

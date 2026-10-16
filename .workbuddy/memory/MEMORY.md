# 项目长期记忆 — RErange（Skill 制作仓库）

## 仓库用途
E:/RErange 是 Skill 制作仓库。首个 Skill：`epub-reorder-clean`（小说 EPUB 章节乱序重排 + 广告网址清理，保证阅读纯净）。

## 项目约定
- Skill 源码放 `epub-reorder-clean/`，打包产物放 `dist/*.skill`，开发测试放 `tests/`（不进 skill 包）。
- 核心脚本坚持纯标准库（zipfile + ElementTree），目标环境零安装成本；中文小说 EPUB 常见 GBK 编码、`&nbsp;` 实体、乱序 spine 都要兼容。
- 改脚本后必须跑 `tests/test_epub_reorder_clean.py`（31 条断言）；发布前跑 make-skill 的 `quick_validate.py --strict`。
- 校验/打包工具需要 PyYAML，用 venv：`C:/Users/19105/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（注意 python.exe 在 Scripts/ 下）。
- 用户偏好：正式交付物修改前先给草稿确认（见用户级 MEMORY.md）。

## 环境备忘
- 测试/运行用受管 Python 3.13.12：`C:/Users/19105/.workbuddy/binaries/python/versions/3.13.12/python.exe`。
- Git Bash 的 `/tmp` 路径 Python 不识别，临时文件用工作区内路径（如 `tests/.debug/`）。

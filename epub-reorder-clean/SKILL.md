---
name: epub-reorder-clean
version: 1.0.0
display_name: EPUB 小说重排与净化
display_name_en: EPUB Novel Reorder & Clean
description: 小说 EPUB 章节乱序重排与广告净化。按章节号（第X章、Chapter N、123.）重排阅读顺序，删除广告网址、短链接、推广文字与纯广告页，同步修正目录和元数据，输出可纯净阅读的 EPUB。适用于用户提供章节顺序混乱或夹带广告的小说 EPUB 需要重排、清理的场景。
description_zh: 小说 EPUB 章节乱序重排与广告净化。按章节号（第X章、Chapter N、123.）重排阅读顺序，删除广告网址、短链接、推广文字与纯广告页，同步修正目录和元数据，输出可纯净阅读的 EPUB。适用于用户提供章节顺序混乱或夹带广告的小说 EPUB 需要重排、清理的场景。
description_en: Reorder scrambled novel EPUB chapters by chapter number and strip advertisement URLs, short links and promo text for clean reading. Use when the user provides a novel EPUB whose chapters are out of order or that contains ad links, short links or pirate-site boilerplate.
---

# EPUB 小说重排与净化

## 概述

把顺序混乱的小说 EPUB 按章节编号重排，并清除广告网址、短链接、推广文字和纯广告页，
输出结构完好、可纯净阅读的新 EPUB。全部逻辑封装在一个本地 Python 脚本中，
只依赖标准库（Python 3.8+），不需要安装任何第三方包。

## 何时使用

适用场景：

- 用户给出小说 EPUB，章节顺序错乱（下载源打乱了章节文件顺序）
- EPUB 正文夹带广告链接、短链接、推广文字、站点水印
- 目录（TOC）顺序与正文不一致
- 元数据残留广告来源（如 dc:source 指向盗版站点）

不适用（遇到时直接说明做不了，不要强行运行）：

- 格式转换（EPUB 转 MOBI/AZW3/PDF 等）——本 Skill 不做转换
- 扫描件/图片型 EPUB（无文本层，无法提取章节标题）
- 已 DRM 加密的 EPUB（需先解密，脚本会报错退出）
- 非 EPUB 文件（PDF/TXT/MOBI/DOCX）

## 工作流

```text
输入 EPUB
  -> 1. 解析 OPF/spine，提取每个章节文件的标题与编号
  -> 2. 按 (卷号, 章号) 稳定排序，生成新阅读顺序
  -> 3. 清理广告：广告链接/短链接/推广文字/广告样式块/裸网址/广告页
  -> 4. 重排目录 toc.ncx 与 nav.xhtml，清理元数据广告字段
  -> 5. 重打包为标准 EPUB（mimetype 首位且不压缩）
  -> 6. 完整性校验（逐文档 XML 复检）
  -> 输出 <书名>_cleaned.epub
```

原文件默认不被修改；每次成功输出都附带 JSON 处理报告（可用 `--report` 落盘）。

## 核心命令

```bash
python scripts/epub_reorder_clean.py <输入.epub> [-o 输出.epub] [选项]
```

| 选项 | 作用 |
|---|---|
| `-o, --output` | 指定输出路径；默认 `<书名>_cleaned.epub` |
| `--in-place` | 原地修改，先把原文件备份为 `.bak` |
| `--dry-run` | 只分析不写文件，用于先给用户看结果 |
| `--no-reorder` | 只清理广告，不重排章节 |
| `--no-clean` | 只重排章节，不清理广告 |
| `--no-text-ads` | 只删广告网址/链接，保留推广文字 |
| `--aggressive` | 删除正文中所有裸网址（默认只删疑似广告网址） |
| `--rules FILE` | 自定义广告规则 JSON（合并或替换内置规则） |
| `--report FILE` | 输出 JSON 处理报告 |
| `--quiet` | 减少终端输出 |

## 执行步骤

1. 确认输入 EPUB 路径；若用户给的是目录或多个文件，先列出让用户选择。
2. 先干跑分析：`--dry-run --report report.json`，把章节顺序变化和广告统计告诉用户。
3. 正式处理：不带 `--dry-run` 运行，输出 `<书名>_cleaned.epub`。
4. 若报告显示 `未识别到章节编号`，说明章节标题没有编号（见下方边界），
   询问用户是否按文件名排序或放弃重排只清理广告（`--no-reorder`）。
5. 汇报：输出路径、重排结果、清除了哪些广告、完整性校验结果。

## 验证成功的标准

- 退出码为 0，摘要最后一行是 `完整性校验: passed`
- 章节顺序报告符合预期（编号章节升序，序章在前、番外/后记在尾）
- 有广告的书广告计数大于 0；干净的书各项计数为 0
- 输出文件能被正常解压，所有 XHTML 可解析（脚本已自检）

## 边界与安全

- 原文件永不被改动，除非显式加 `--in-place`（此时自动生成 `.bak` 备份）。
- 只删除命中广告规则的内容；站内相对链接、`#` 锚点、`mailto:` 等永不触碰。
- 广告链接文本超过 200 字时只摘除 href 属性、不删元素，防止误删正文。
- 纯广告页移除判定：原文本命中广告规则 + 清理后无媒体 + 残留不超过 50 字且清除比例不低于 75%。
- 解析失败的文件保持原样并在报告里告警；失败数过半时视为 DRM 或损坏文件，直接报错退出。
- 编码按原样回写：UTF-8（含 BOM）、GBK/GB18030、UTF-16 均保留原编码。
- 已知限制：跨多个文本节点拆开的广告文字（如 `本书由<b>XX</b>整理`）只能部分清除；
  非 XHTML 的 HTML 文件无法安全清理，会保持原样。

## 资源路由

- [scripts/epub_reorder_clean.py](scripts/epub_reorder_clean.py) —— 唯一需要执行的脚本，纯标准库，命令行自足。
- [references/ordering-rules.md](references/ordering-rules.md) —— 章节号识别格式、排序规则、序章/番外归位逻辑、跳过重排的条件。需要解释"为什么这样排"或调整排序行为时阅读。
- [references/ad-rules.md](references/ad-rules.md) —— 内置广告规则清单、`--rules` 自定义规则格式、明确不会删除的内容。用户报告漏删或误删时阅读并按需自定义规则。

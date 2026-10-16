# RErange — EPUB 小说重排与净化 Skill

把顺序混乱的小说 EPUB 按章节编号重排，并清除广告网址、短链接、推广文字和纯广告页，
输出结构完好、可纯净阅读的新 EPUB。封装为一个 Agent Skill（触发词 **RErange**），
任意兼容 Skill 的 AI Agent（WorkBuddy、Claude Code 等）安装后即可用自然语言触发。

- 零依赖：单个 Python 脚本，仅用标准库（Python 3.8+），无需安装第三方包
- 安全：默认不修改原文件，输出 `书名_cleaned.epub`；输出前逐文档 XML 完整性校验
- 兼容：UTF-8 / GBK / UTF-16 编码、`&nbsp;` 等实体、EPUB 2（toc.ncx）与 EPUB 3（nav.xhtml）

## 功能

| 能力 | 说明 |
| --- | --- |
| 章节重排 | 识别 `第X章/回/节/话`（中文数字 + 阿拉伯数字）、`第X卷/部/册`、`Chapter N`、行首数字、文件名编号；按 (卷, 章) 排序；序章/楔子置顶，番外/后记置尾，无编号内容锚定相邻章节 |
| 广告净化 | 广告域名链接、短链接（t.cn 等）、推广文字（"本书由XX整理""无弹窗阅读"等盗版站 boilerplate）、广告样式块、正文裸网址、纯广告页整页移出阅读顺序 |
| 连带修复 | toc.ncx / nav.xhtml 目录同步重排、OPF 元数据广告来源字段清除 |
| 可控选项 | `--dry-run` 预览、`--aggressive` 删除全部裸网址、`--no-reorder` / `--no-clean` 单功能模式、自定义规则文件 |

## 仓库结构

```
RErange/
├── rerange/                        # Skill 源码（即 skill 目录本身）
│   ├── SKILL.md                    # 技能定义（name: rerange，触发词 RErange）
│   ├── scripts/
│   │   └── epub_reorder_clean.py   # 全部逻辑，纯标准库
│   ├── references/                 # 排序规则 / 广告规则参考文档
│   │   ├── ordering-rules.md
│   │   └── ad-rules.md
│   ├── agents/
│   │   └── openai.yaml             # UI 元数据
│   └── evals/
│       └── evals.json              # 评测用例（含 RErange 触发词用例）
├── dist/
│   └── rerange.skill               # 可安装的 Skill 包（约 24 KB）
├── tests/                          # 开发测试（不进 skill 包）
│   ├── make_test_epubs.py          # 合成测试 EPUB 生成器
│   └── test_epub_reorder_clean.py  # 31 条断言端到端测试
├── .gitattributes                  # 文本文件 LF 归一化
├── .gitignore                      # 忽略缓存 / 本地记忆 / 测试产物
├── LICENSE                         # MIT
└── README.md
```

## 安装

### WorkBuddy（用户级，所有项目可用）

```bash
# Linux / macOS / Git Bash
git clone --depth 1 https://github.com/Yjiutong/RErange.git /tmp/RErange
cp -r /tmp/RErange/rerange ~/.workbuddy/skills/
```

```powershell
# Windows PowerShell
git clone --depth 1 https://github.com/Yjiutong/RErange.git $env:TEMP\RErange
Copy-Item -Recurse "$env:TEMP\RErange\rerange" "$HOME\.workbuddy\skills\"
```

没有 git 时可直接下载压缩包：

```bash
curl -L https://github.com/Yjiutong/RErange/archive/refs/heads/main.tar.gz | tar -xz
cp -r RErange-main/rerange ~/.workbuddy/skills/
```

### WorkBuddy（项目级，随仓库共享给团队）

```bash
git clone --depth 1 https://github.com/Yjiutong/RErange.git /tmp/RErange
mkdir -p .workbuddy/skills
cp -r /tmp/RErange/rerange .workbuddy/skills/
```

### 其他兼容 Skill 的 Agent（Claude Code 等）

目录约定相同，把 `rerange/` 复制到对应 skills 目录即可，例如
Claude Code 的用户级目录 `~/.claude/skills/`：

```bash
git clone --depth 1 https://github.com/Yjiutong/RErange.git /tmp/RErange
cp -r /tmp/RErange/rerange ~/.claude/skills/
```

### 安装 .skill 包（WorkBuddy 技能面板上传）

下载仓库中的打包产物，在「技能 → 添加技能 → 上传技能」中选择即可：

```
https://github.com/Yjiutong/RErange/raw/main/dist/rerange.skill
```

安装完成后无需额外配置，对 Agent 说「**用 RErange 把这本 EPUB 章节重排并清掉广告**」
或直接描述需求（章节乱序 / 有广告）即可触发。

## 使用

自然语言触发（安装 Skill 后）：

> 用 RErange 处理这本《下山》EPUB，章节顺序全乱了，里面的广告网址也删掉

也可以直接调用脚本：

```bash
python rerange/scripts/epub_reorder_clean.py 输入.epub -o 输出.epub
python rerange/scripts/epub_reorder_clean.py 输入.epub --dry-run   # 只看不改
python rerange/scripts/epub_reorder_clean.py --help               # 全部选项
```

## 开发与测试

```bash
python tests/make_test_epubs.py tests/.debug   # 生成合成测试 EPUB
python tests/test_epub_reorder_clean.py        # 31 条断言端到端测试
```

## License

MIT，见 [LICENSE](LICENSE)。

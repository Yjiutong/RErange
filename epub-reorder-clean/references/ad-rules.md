# 广告识别与清理规则

本文件说明内置广告规则、`--rules` 自定义方式，以及明确不会删除的内容。
当用户报告漏删或误删时阅读本文件。

## 1. URL 判定（is_ad_href）

对 `a[href]`、`img/iframe[src]`、正文裸网址、OPF 元数据字段生效：

- **站内链接永不判定为广告**：相对路径、`#` 锚点、`mailto:`、`tel:`、`javascript:`、`data:`。
- **主机标签命中广告词**：host 的点分标签中出现
  `ad ads adv advert adserver adservice advertise advertisement click clicks track
  tracker tracking cpc cpm cps union promo promotion banner banners sponsor
  sponsored popup popunder pop redirect`。
- **已知短链接域名**：`t.cn`、`url.cn`、`dwz.cn`、`suo.im`、`suo.la`、`mrw.so`（含子域）。
- **主机包含盗版站/聚合站特征串**：biquge、biqudao、bxwx、luoxia、23us、lewendu、
  kenwen、ptwxz、shumilou、81zw、bixiabook、biquta、duquan、xs8、paozha 等
  （完整清单见脚本 `DEFAULT_AD_HOST_SUBSTRINGS`）。

## 2. 正文裸网址

默认只删除**命中上述广告规则**的裸网址（`http://`、`https://`、`www.` 开头）。
`--aggressive` 下删除所有裸网址。删除后会顺带清理空括号和重复标点。

## 3. 推广文字（text_patterns）

默认清理的小说站点 boilerplate，包括：

- `本书由XX整理/提供/支持/赞助`
- `更多好书请访问/关注/下载`
- `无弹窗/无广告/清爽/全文阅读`
- `txt小说下载/打包`
- `网盘下载/地址/链接`
- `关注微信公众号`
- `QQ群/读者群/书友群 + 群号`
- `请记住本书网址/域名`
- `求收藏/推荐/投票/打赏`
- `百度贴吧/网盘`
- `手机版阅读/访问`
- `本站推荐/请访问`
- 盗版站点名（笔趣阁、顶点小说、八一中文等）

用 `--no-text-ads` 可完全跳过文字清理，只处理网址。

## 4. 广告样式块与广告页

- `class`/`id` 命中广告词（ad、ads、banner、sponsor、promo、popup 等）的元素，
  仅当内容为空、命中推广文字或含广告链接时才移除。
- 纯广告页从阅读顺序移除的判定（三条同时满足）：
  1. 原文本命中推广文字规则；
  2. 清理后文档无媒体元素（img/svg/audio/video 等）；
  3. 残留文本不超过 50 字，且被清除比例不低于 75%。

第 3 条保证夹带广告的正常章节不会被误删——正常章节清理后残留的正文远大于 50 字。

## 5. 目录与元数据

- `toc.ncx`：`content src` 是广告链接、或 `navLabel` 文字命中推广规则的 navPoint 整个移除；
  重排后按新顺序重编 `playOrder`。
- `nav.xhtml`：只重排 `epub:type="toc"` 的 nav（landmarks/page-list 不排）；
  指向已移除广告页的目录项一并移除。
- OPF 元数据：`dc:source/publisher/rights/description/subject/identifier` 等字段
  文本是广告 URL 或命中推广规则时移除该字段。

## 6. 自定义规则（--rules）

```json
{
  "mode": "merge",
  "ad_host_labels": ["mylabel"],
  "shorteners": ["xx.cn"],
  "ad_host_substrings": ["xxsite"],
  "text_patterns": ["正则字符串"]
}
```

- `mode`：`merge`（默认，在内置规则基础上追加）或 `replace`（完全替换该类规则）。
- `text_patterns` 是 Python 正则，写法与内置列表一致；非法正则会报错退出。
- 想保留某类内置文字规则，用 `replace` 模式给出精简列表。

## 7. 明确不会删除的内容

- 站内相对链接与锚点（含站内跳转、返回上一章）。
- 非广告外链（如作者主页、正常引用链接）。
- 正常正文，包括提到"广告"二字的正文。
- 无广告的章节，即使标题不含编号。
- 无法按 XML 解析的文件（保持原样，仅在报告里告警）。

## 8. 已知边界

- 跨文本节点拆开的广告文字（`本书由<b>XX</b>整理`）只能清除命中规则的片段。
- 广告特征库以中文盗版小说站为主，换语种或小众站点可能漏判，用 `--rules` 补充。
- 图片类广告只处理 src 命中广告规则的 `<img>`；普通配图不受影响。

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EPUB 小说章节重排 + 广告网址清理工具（仅依赖 Python 标准库）。

功能：
1. 按章节编号重排阅读顺序，支持：第X章/回/节/话/幕/篇/集、第X卷/部/册、
   阿拉伯数字前缀（"123." "123、" "001.html"）、Chapter/CH 12 等写法；
   卷号与章号组合排序（卷一+第X章），无编号条目（序章/番外/后记）智能归位。
2. 删除广告内容：广告域名链接、短链接、推广文字、广告样式块、正文裸网址
   （默认只删疑似广告网址，--aggressive 删除全部裸网址）。
3. 同步重排目录（toc.ncx / nav.xhtml）到新的阅读顺序，清理 OPF 元数据中的
   广告来源，移除纯广告页。
4. 重新打包为标准 EPUB（mimetype 首位且不压缩），写出前做完整性校验。

用法：
    python epub_reorder_clean.py 输入.epub [-o 输出.epub] [选项]

仅支持 Python 3.8+，无第三方依赖。
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

XHTML_NS = "http://www.w3.org/1999/xhtml"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
EPUB_OPS_NS = "http://www.idpf.org/2007/ops"

# 序列化时使用的固定前缀（等价变换，不影响阅读器解析）
ET.register_namespace("", XHTML_NS)
ET.register_namespace("opf", OPF_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("dcterms", DCTERMS_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
ET.register_namespace("svg", "http://www.w3.org/2000/svg")
ET.register_namespace("epub", EPUB_OPS_NS)

BIG = 10 ** 9  # 排序哨兵值

# --------------------------------------------------------------------------
# HTML 实体预处理（expat 不识别 XHTML 实体名，需转为数字引用）
# --------------------------------------------------------------------------

ENTITY_MAP = {
    "nbsp": 160, "iexcl": 161, "cent": 162, "pound": 163, "curren": 164,
    "yen": 165, "brvbar": 166, "sect": 167, "uml": 168, "copy": 169,
    "ordf": 170, "laquo": 171, "not": 172, "shy": 173, "reg": 174,
    "macr": 175, "deg": 176, "plusmn": 177, "sup2": 178, "sup3": 179,
    "acute": 180, "micro": 181, "para": 182, "middot": 183, "cedil": 184,
    "sup1": 185, "ordm": 186, "raquo": 187, "frac14": 188, "frac12": 189,
    "frac34": 190, "iquest": 191, "Agrave": 192, "Aacute": 193, "Acirc": 194,
    "Atilde": 195, "Auml": 196, "Aring": 197, "AElig": 198, "Ccedil": 199,
    "Egrave": 200, "Eacute": 201, "Ecirc": 202, "Euml": 203, "Igrave": 204,
    "Iacute": 205, "Icirc": 206, "Iuml": 207, "ETH": 208, "Ntilde": 209,
    "Ograve": 210, "Oacute": 211, "Ocirc": 212, "Otilde": 213, "Ouml": 214,
    "times": 215, "Oslash": 216, "Ugrave": 217, "Uacute": 218, "Ucirc": 219,
    "Uuml": 220, "Yacute": 221, "THORN": 222, "szlig": 223, "agrave": 224,
    "aacute": 225, "acirc": 226, "atilde": 227, "auml": 228, "aring": 229,
    "aelig": 230, "ccedil": 231, "egrave": 232, "eacute": 233, "ecirc": 234,
    "euml": 235, "igrave": 236, "iacute": 237, "icirc": 238, "iuml": 239,
    "eth": 240, "ntilde": 241, "ograve": 242, "oacute": 243, "ocirc": 244,
    "otilde": 245, "ouml": 246, "divide": 247, "oslash": 248, "ugrave": 249,
    "uacute": 250, "ucirc": 251, "uuml": 252, "yacute": 253, "thorn": 254,
    "yuml": 255, "ensp": 8194, "emsp": 8195, "thinsp": 8201, "ndash": 8211,
    "mdash": 8212, "lsquo": 8216, "rsquo": 8217, "sbquo": 8218, "ldquo": 8220,
    "rdquo": 8221, "bdquo": 8222, "dagger": 8224, "Dagger": 8225, "bull": 8226,
    "hellip": 8230, "permil": 8240, "prime": 8242, "Prime": 8243, "lsaquo": 8249,
    "rsaquo": 8250, "oline": 8254, "frasl": 8260, "euro": 8364, "trade": 8482,
    "larr": 8592, "uarr": 8593, "rarr": 8594, "darr": 8595, "harr": 8596,
    "infin": 8734, "ne": 8800, "le": 8804, "ge": 8805, "hearts": 9829,
    "diams": 9830, "clubs": 9827, "spades": 9824, "zwj": 8205, "zwnj": 8204,
    "lrm": 8206, "rlm": 8207,
}

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>", re.S)
_ENTITY_RE = re.compile(r"&(#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")


def strip_xml_decl(text):
    return _XML_DECL_RE.sub("", text, count=1)


def preprocess_entities(text):
    """把具名 HTML 实体转成数字引用；未知实体原样保留（随后解析失败会安全跳过）。"""
    def repl(m):
        token = m.group(1)
        if token.startswith("#"):
            return m.group(0)
        cp = ENTITY_MAP.get(token)
        if cp is None:
            return m.group(0)
        return "&#%d;" % cp
    return _ENTITY_RE.sub(repl, text)


def detect_encoding(raw):
    """返回 (编码名, 是否有 UTF-8 BOM)。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8", True
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16", False
    m = re.match(rb"^\s*<\?xml[^>]*encoding=[\"']([\w\-]+)[\"']", raw[:256])
    if m:
        return m.group(1).decode("ascii", "replace"), False
    m = re.search(rb"charset=[\"']?([\w\-]+)", raw[:4096])
    if m:
        return m.group(1).decode("ascii", "replace"), False
    try:
        raw.decode("utf-8")
        return "utf-8", False
    except UnicodeDecodeError:
        return "gb18030", False


# --------------------------------------------------------------------------
# XML 文档读写
# --------------------------------------------------------------------------

class EpubError(Exception):
    """用户可读的 EPUB 处理错误。"""


def read_xml_doc(zf, name):
    """读取并解析 zip 内文档。返回 (root, enc, bom, error, raw_bytes)。"""
    try:
        raw = zf.read(name)
    except Exception as exc:  # noqa: BLE001
        return None, "utf-8", False, str(exc), b""
    enc, bom = detect_encoding(raw)
    try:
        text = raw.decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        enc, bom = "utf-8", False
        text = raw.decode("utf-8", errors="replace")
    text = strip_xml_decl(text)
    text = preprocess_entities(text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return None, enc, bom, str(exc), raw
    return root, enc, bom, None, raw


def serialize_xml_doc(root, enc, bom):
    body = ET.tostring(root, encoding="unicode")
    enc_norm = enc.lower().replace("_", "-")
    if enc_norm in ("utf-8", "utf8", "ascii", "us-ascii"):
        data = body.encode("utf-8", errors="xmlcharrefreplace")
        if bom:
            data = b"\xef\xbb\xbf" + data
        return b'<?xml version="1.0" encoding="utf-8"?>\n' + data
    try:
        data = body.encode(enc, errors="xmlcharrefreplace")
    except (LookupError, UnicodeEncodeError):
        data = body.encode("utf-8", errors="xmlcharrefreplace")
        enc = "utf-8"
    return ('<?xml version="1.0" encoding="%s"?>\n' % enc).encode("ascii") + data


def localname(tag):
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


# --------------------------------------------------------------------------
# 章节编号解析
# --------------------------------------------------------------------------

CN_DIGIT = {
    "零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "贰": 2, "三": 3, "叁": 3,
    "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陆": 6, "七": 7, "柒": 7,
    "八": 8, "捌": 8, "九": 9, "玖": 9, "十": 10, "拾": 10, "百": 100, "佰": 100,
    "千": 1000, "仟": 1000, "万": 10000, "萬": 10000, "两": 2, "兩": 2,
}
CN_CHARS = "".join(CN_DIGIT.keys())

CHAP_KINDS = "章回节话話幕则篇集"
VOL_KINDS = "卷部册"
CHAP_RE = re.compile(r"第\s*(\d{1,5}|[%s]{1,12})\s*[%s]" % (CN_CHARS, CHAP_KINDS))
VOL_RE = re.compile(r"第\s*(\d{1,3}|[%s]{1,12})\s*[%s]" % (CN_CHARS, VOL_KINDS))
LEAD_NUM_RE = re.compile(r"^\s*(\d{1,4})\s*[.、:：]")
EN_CHAP_RE = re.compile(r"(?<![A-Za-z])(?:chapter|chap|ch)\.?\s*(\d{1,5})\b", re.IGNORECASE)
STEM_NUM_RE = re.compile(r"^(\d{1,5})(?:[_\-. ].*)?$")


def cn2num(s):
    """中文数字转整数，失败返回 None。"""
    total, section, num, seen = 0, 0, 0, False
    for ch in s:
        v = CN_DIGIT.get(ch)
        if v is None:
            return None
        seen = True
        if v == 10:
            if num == 0:
                num = 1
            section += num * 10
            num = 0
        elif v == 100:
            if num == 0:
                num = 1
            section += num * 100
            num = 0
        elif v == 1000:
            if num == 0:
                num = 1
            section += num * 1000
            num = 0
        elif v == 10000:
            section = (section + num) * 10000
            total += section
            section, num = 0, 0
        else:
            num = v
    if not seen:
        return None
    return total + section + num


def _num(token):
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    return cn2num(token)


def parse_numbering(title, filename=""):
    """从标题/文件名提取 (卷号, 章号)，解析不到返回 (None, None)。"""
    chap = vol = None
    sources = [title or ""]
    if filename:
        sources.append(Path(filename).stem)
    for src in sources:
        if not src:
            continue
        if chap is None:
            m = CHAP_RE.search(src)
            if m:
                chap = _num(m.group(1))
        if vol is None:
            m = VOL_RE.search(src)
            if m:
                vol = _num(m.group(1))
        if chap is None:
            m = EN_CHAP_RE.search(src)
            if m:
                chap = int(m.group(1))
        if chap is None:
            m = LEAD_NUM_RE.search(src)
            if m:
                chap = int(m.group(1))
        if chap is None:
            m = STEM_NUM_RE.match(src.strip())
            if m:
                chap = int(m.group(1))
        if chap is not None and vol is not None:
            break
    return vol, chap


FRONT_KEYWORDS = (
    "序章", "序言", "序曲", "序诗", "序一", "序二", "序三", "序四", "卷首语",
    "前言", "楔子", "引子", "引言", "简介", "内容简介", "作品相关", "作者的话",
    "写在前面", "写在之前", "写在开头", "阅读须知", "导读", "郑重声明",
    "告读者", "开篇", "序",
)
BACK_KEYWORDS = (
    "番外", "外传", "尾声", "后记", "编后记", "终章", "最终章", "大结局",
    "完结感言", "完本感言", "完本寄语", "感言", "写在最后", "写在结尾",
    "附录", "年表", "人物设定", "设定集", "人物志", "彩蛋", "谢词", "致谢",
    "后传", "续篇", "最新通知", "重要通知", "本书公告", "结局",
)


def matter_kind(title):
    """识别前置/后记类条目（仅对无编号条目生效）。"""
    t = (title or "").strip()
    if not t:
        return None
    for kw in FRONT_KEYWORDS:
        if t.startswith(kw):
            return "front"
    for kw in BACK_KEYWORDS:
        if t.startswith(kw):
            return "back"
    return None


_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def extract_title(root):
    """从文档提取章节标题：优先第一个标题元素，其次 title，再其次首个段落。"""
    for el in root.iter():
        if localname(el.tag) in ("h1", "h2", "h3", "h4", "h5", "h6"):
            t = " ".join("".join(el.itertext()).split())
            if t:
                return t
    for el in root.iter():
        if localname(el.tag) == "title":
            t = " ".join("".join(el.itertext()).split())
            if t:
                return t
    for el in root.iter():
        if localname(el.tag) == "p":
            t = " ".join("".join(el.itertext()).split())
            if t:
                return t[:60]
    return ""


def extract_title_regex(text):
    """XML 解析失败时的正则兜底提取标题。"""
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    if m:
        t = " ".join(_TAG_STRIP_RE.sub("", m.group(1)).split())
        if t:
            return t
    m = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", text, re.I | re.S)
    if m:
        t = " ".join(_TAG_STRIP_RE.sub("", m.group(1)).split())
        if t:
            return t
    return ""


# --------------------------------------------------------------------------
# 重排算法
# --------------------------------------------------------------------------

def compute_new_order(items):
    """items: [{index, id, title, path, vol, chap}]。
    返回 (new_id_list 或 None, info_dict)。"""
    total = len(items)
    numbered = [it for it in items if it["chap"] is not None]
    if len(numbered) < 2 or len(numbered) * 2 < total:
        return None, {
            "performed": False,
            "reason": "no-chapter-numbers" if not numbered else "insufficient-chapter-numbers",
            "numbered": len(numbered),
            "total": total,
        }
    has_vol = any(it["vol"] is not None for it in items)
    cur_vol = 0
    keys = {}
    anchor_seq = 0
    last = None  # (vol, chap, index)
    for it in items:
        if it["vol"] is not None:
            cur_vol = it["vol"]
        eff_vol = cur_vol if has_vol else 0
        if it["chap"] is not None:
            keys[it["index"]] = (eff_vol, it["chap"], 0, it["index"], 0)
            last = (eff_vol, it["chap"], it["index"])
            anchor_seq = 0
        else:
            kind = matter_kind(it["title"])
            if kind == "front" or last is None:
                keys[it["index"]] = (-1, 0, 0, it["index"], 0)
            elif kind == "back":
                keys[it["index"]] = (BIG, 0, 0, it["index"], 0)
            else:
                anchor_seq += 1
                keys[it["index"]] = (last[0], last[1], 1, last[2], anchor_seq)
    ordered = sorted(items, key=lambda it: keys[it["index"]])
    return [it["id"] for it in ordered], {
        "performed": True,
        "numbered": len(numbered),
        "total": total,
    }


# --------------------------------------------------------------------------
# 广告规则
# --------------------------------------------------------------------------

DEFAULT_AD_LABELS = {
    "ad", "ads", "adv", "advert", "adverts", "adserver", "adservice", "adserv",
    "advertise", "advertisement", "click", "clicks", "track", "tracker",
    "tracking", "cpc", "cpm", "cps", "union", "promo", "promotion", "banner",
    "banners", "sponsor", "sponsored", "popup", "popunder", "pop", "redirect",
}
DEFAULT_SHORTENERS = {"t.cn", "url.cn", "dwz.cn", "suo.im", "suo.la", "mrw.so"}
DEFAULT_AD_HOST_SUBSTRINGS = (
    "biquge", "biqudao", "bxwx", "luoxia", "23us", "lewendu", "kenwen",
    "ptwxz", "shumilou", "81zw", "bixiabook", "biquta", "duquan", "xs8",
    "paozha", "hanwuji", "jiuzhai", "hongyeshan", "ruochu", "zhijianliwen",
    "aixiawx", "shuhaige", "xxbiquge", "newbiquge", "mianbook", "txtx",
    "xstt5", "quanben5", "ibiquge", "heiyan", "zhangjiwu", "ciweimao",
    "wutuxs", "haxwx", "ppxsk", "biquke", "shuba", "ptxt", "bqg",
)
DEFAULT_SITE_NAMES = (
    "笔趣阁", "顶点小说", "八一中文", "零点看书", "恋上你看书", "完本神站",
    "全本小说网", "热门小说网", "就爱中文", "书客居", "闪文书", "龙阅读",
)
DEFAULT_TEXT_PATTERNS = [
    r"本书由[^，。！？<>]{0,40}?(?:整理|提供|支持|赞助|录入|校对|制作|上传)",
    r"(?:更多|海量|大量|精彩)?(?:好书|小说|全本|全集|热门)(?:请|尽在|欢迎|敬请)?[^，。！？<>\n]{0,24}?(?:访问|关注|下载|阅读|在线|进入|收藏本站)",
    r"[^，。！？<>\n]{0,20}?(?:无弹窗|无广告|清爽|全文|全集|全本)阅读[^，。！？<>\n]{0,20}",
    r"(?:txt|TXT|Txt|电子书)(?:小说|全集|下载|打包|分享)[^，。！？<>\n]{0,20}",
    r"网盘(?:下载|地址|链接)[^，。！？<>\n]{0,40}",
    r"关注(?:微信公众号|公众号|微信|weixin|WeChat)[^，。！？<>\n]{0,30}",
    r"(?:QQ|读者|书友|作者|交流)群(?:号|号码)?[:：]?\s*\d{5,12}",
    r"请记住(?:本书|本文|本站)?(?:的)?(?:最新)?(?:网址|域名|网站)",
    r"(?:请|麻烦|求|希望各位|大家)(?:收藏|推荐|投票|打赏|支持)(?:本书|一下|个|本站)?",
    r"百度(?:贴吧|网盘)[^，。！？<>\n]{0,40}",
    r"手机(?:版|用户)?(?:阅读|浏览|访问)[^，。！？<>\n]{0,40}",
    r"(?:本站|本网站|网站)?推荐(?:以下|下面|几本)?(?:好书|小说|作品|完本)",
    r"请访问[^，。！？<>\n]{0,30}",
    r"(?:本站|本网站)(?:所有|提供)?(?:小说|内容|作品)[^，。！？<>\n]{0,30}?(?:转载|收集|整理|来自互联网|仅供)",
    r"(?:%s)" % "|".join(re.escape(n) for n in DEFAULT_SITE_NAMES),
]

_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_URL_CHARS = r"[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]"
BARE_URL_RE = re.compile(
    r"(?<![A-Za-z0-9@/.])"
    r"((?:https?://|www\.)%s{4,})" % _URL_CHARS
)
_EMPTY_PAREN_RE = re.compile(r"[（(]\s*[）)]")
_REPEAT_PUNCT_RE = re.compile(r"([。！？，、；：])\1+")
_WORD_CHAR_RE = re.compile(r"[0-9A-Za-z\u3400-\u9fff]")


class Rules:
    """广告判定规则集合。"""

    def __init__(self, labels, shorteners, substrings, text_patterns):
        self.labels = frozenset(labels)
        self.shorteners = frozenset(shorteners)
        self.substrings = tuple(substrings)
        self.text_patterns = list(text_patterns)

    @classmethod
    def defaults(cls, use_text=True):
        patterns = [re.compile(p) for p in DEFAULT_TEXT_PATTERNS] if use_text else []
        return cls(DEFAULT_AD_LABELS, DEFAULT_SHORTENERS,
                   DEFAULT_AD_HOST_SUBSTRINGS, patterns)

    @classmethod
    def load(cls, path, use_text=True):
        """从 JSON 文件加载自定义规则；mode=replace 时整体替换内置规则。"""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise EpubError("无法读取规则文件 %s: %s" % (path, exc))
        if not isinstance(data, dict):
            raise EpubError("规则文件必须是 JSON 对象")
        replace = str(data.get("mode", "merge")).lower() == "replace"

        def pick(key, default):
            values = data.get(key)
            if values is None:
                return default
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise EpubError("规则字段 %s 必须是字符串数组" % key)
            if replace:
                return values
            return list(default) + values

        labels = pick("ad_host_labels", sorted(DEFAULT_AD_LABELS))
        shorteners = pick("shorteners", sorted(DEFAULT_SHORTENERS))
        substrings = pick("ad_host_substrings", list(DEFAULT_AD_HOST_SUBSTRINGS))
        raw_patterns = pick("text_patterns", list(DEFAULT_TEXT_PATTERNS))
        if not use_text:
            raw_patterns = []
        patterns = []
        for p in raw_patterns:
            try:
                patterns.append(re.compile(p))
            except re.error as exc:
                raise EpubError("规则 text_patterns 含非法正则 %r: %s" % (p, exc))
        return cls(labels, shorteners, substrings, patterns)


def is_ad_href(href, rules):
    """判断 URL 是否为广告/短链接。相对链接与非 HTTP 协议一律视为内部链接。"""
    h = (href or "").strip()
    if not h:
        return False
    if h.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return False
    if h.startswith("//"):
        host = h[2:]
    else:
        m = _URL_SCHEME_RE.match(h)
        if not m:
            return False  # 站内相对链接
        host = h[m.end():]
    host = host.split("@")[-1].split("/")[0].split("?")[0].split("#")[0]
    host = host.split(":")[0].strip().lower().rstrip(".")
    if not host:
        return False
    labels = host.split(".")
    if any(l in rules.labels for l in labels):
        return True
    if host in rules.shorteners:
        return True
    if any(host.endswith("." + s) for s in rules.shorteners):
        return True
    return any(s in host for s in rules.substrings)


# --------------------------------------------------------------------------
# 内容清理
# --------------------------------------------------------------------------

class CleanStats:
    _FIELDS = ("links_removed", "images_removed", "iframes_removed",
               "text_ads_removed", "urls_removed", "elements_removed",
               "navpoints_removed", "metadata_fields_removed")

    def __init__(self):
        self.files_modified = 0
        for f in self._FIELDS:
            setattr(self, f, 0)

    def snapshot(self):
        return {f: getattr(self, f) for f in self._FIELDS}

    def as_dict(self):
        d = {"files_modified": self.files_modified}
        d.update(self.snapshot())
        return d


REMOVABLE_EMPTY_TAGS = {
    "p", "div", "span", "li", "ul", "ol", "a", "h1", "h2", "h3", "h4", "h5",
    "h6", "section", "aside", "blockquote", "figure", "figcaption", "td", "tr",
    "table", "dl", "dt", "dd", "font", "center", "small", "em", "strong", "b",
    "i", "u",
}
MEDIA_TAGS = {"img", "image", "svg", "audio", "video", "iframe", "object",
              "embed", "canvas", "picture", "br"}
AD_CLASS_TOKENS = {"ad", "ads", "adv", "advert", "banner", "sponsor", "promo",
                   "popup", "float", "fixed", "advertisement"}
MAX_ANCHOR_TEXT = 200  # 链接文本超过此长度只摘除 href，不删元素，防止误删正文


def remove_element(parent, child):
    """移除子元素并保留其尾部文本，避免文字粘连丢失。"""
    idx = list(parent).index(child)
    tail = child.tail or ""
    if idx == 0:
        parent.text = (parent.text or "") + tail
    else:
        prev = parent[idx - 1]
        prev.tail = (prev.tail or "") + tail
    parent.remove(child)


def element_is_empty(el):
    if len(el) > 0:
        return False
    return not (el.text or "").strip()


def clean_text(text, rules, aggressive, stats):
    if not text:
        return text
    original = text
    for pat in rules.text_patterns:
        text = pat.sub("", text)

    def url_repl(m):
        url = m.group(1).rstrip(".,;:!?")
        probe = url if "://" in url else "http://" + url
        if aggressive or is_ad_href(probe, rules):
            stats.urls_removed += 1
            return ""
        return m.group(1)

    text = BARE_URL_RE.sub(url_repl, text)
    if text == original:
        return text
    stats.text_ads_removed += 1
    text = _EMPTY_PAREN_RE.sub("", text)
    text = _REPEAT_PUNCT_RE.sub(r"\1", text)
    if not _WORD_CHAR_RE.search(text):
        return ""  # 清理后只剩标点/空白，置空以便上层元素被移除
    return text


def is_ad_content(el, rules):
    """class/id 命中广告样式的元素，仅当内容确实是广告时才移除。"""
    text = "".join(el.itertext()).strip()
    if not text:
        return True
    for pat in rules.text_patterns:
        if pat.search(text):
            return True
    for d in el.iter():
        ln = localname(d.tag)
        if ln in ("a", "img", "iframe"):
            u = d.get("href") or d.get("src") or ""
            if u and is_ad_href(u, rules):
                return True
    return False


def clean_tree(el, parent, rules, aggressive, stats):
    """后序遍历清理：先处理子元素，再处理自身。"""
    for child in list(el):
        clean_tree(child, el, rules, aggressive, stats)

    tag = localname(el.tag)
    if not tag:
        return

    if tag == "a":
        href = el.get("href") or ""
        text = "".join(el.itertext()).strip()
        if is_ad_href(href, rules):
            if len(text) > MAX_ANCHOR_TEXT:
                # 链接文本过长，疑似包裹正文：只摘除链接属性
                if "href" in el.attrib:
                    del el.attrib["href"]
                    stats.links_removed += 1
            elif parent is not None:
                remove_element(parent, el)
                stats.links_removed += 1
                return
    elif tag in ("img", "iframe"):
        src = el.get("src") or ""
        if src and is_ad_href(src, rules) and parent is not None:
            remove_element(parent, el)
            if tag == "img":
                stats.images_removed += 1
            else:
                stats.iframes_removed += 1
            return

    cls_attr = " ".join([el.get("class") or "", el.get("id") or ""]).lower()
    if cls_attr:
        tokens = set(re.split(r"[\s,;:]+", cls_attr))
        if tokens & AD_CLASS_TOKENS and is_ad_content(el, rules):
            if parent is not None:
                remove_element(parent, el)
                stats.elements_removed += 1
                return

    if el.text:
        el.text = clean_text(el.text, rules, aggressive, stats)
    for child in el:
        if child.tail:
            child.tail = clean_text(child.tail, rules, aggressive, stats)

    if tag in REMOVABLE_EMPTY_TAGS and element_is_empty(el) and parent is not None:
        remove_element(parent, el)
        stats.elements_removed += 1


def clean_ncx(root, rules, stats):
    """清理 toc.ncx：移除广告 navPoint、清理导航文字。"""
    for navmap in root.iter():
        if localname(navmap.tag) != "navMap":
            continue
        _clean_navmap(navmap, rules, stats)
        for el in navmap.iter():
            if localname(el.tag) == "text" and el.text:
                el.text = clean_text(el.text, rules, False, stats)


def _clean_navmap(container, rules, stats):
    for child in list(container):
        if localname(child.tag) != "navPoint":
            continue
        if _navpoint_is_ad(child, rules):
            remove_element(container, child)
            stats.navpoints_removed += 1
            continue
        _clean_navmap(child, rules, stats)


def _navpoint_is_ad(np_el, rules):
    for d in np_el.iter():
        ln = localname(d.tag)
        if ln == "content":
            src = d.get("src") or ""
            if src and is_ad_href(src, rules):
                return True
        elif ln == "text":
            t = "".join(d.itertext())
            if any(p.search(t) for p in rules.text_patterns):
                return True
    return False


CLEANABLE_META = {"source", "publisher", "rights", "description", "subject",
                  "contributor", "identifier", "relation", "coverage", "type"}


def clean_opf_metadata(metadata_el, rules, stats):
    """清理 OPF 元数据中的广告来源字段。"""
    if metadata_el is None:
        return False
    changed = False
    for child in list(metadata_el):
        if localname(child.tag) not in CLEANABLE_META:
            continue
        text = "".join(child.itertext()).strip()
        if not text:
            continue
        is_ad = False
        if _URL_SCHEME_RE.match(text) or text.startswith("www."):
            is_ad = is_ad_href(text if "://" in text else "http://" + text, rules)
        if not is_ad:
            is_ad = any(p.search(text) for p in rules.text_patterns)
        if is_ad:
            remove_element(metadata_el, child)
            stats.metadata_fields_removed += 1
            changed = True
    return changed


def document_is_empty(root):
    if "".join(root.itertext()).strip():
        return False
    for el in root.iter():
        if localname(el.tag) in MEDIA_TAGS:
            return False
    return True


# --------------------------------------------------------------------------
# 目录重排
# --------------------------------------------------------------------------

def resolve_nav_href(href, base_dir):
    h = unquote((href or "").split("#", 1)[0].strip())
    if not h or _URL_SCHEME_RE.match(h):
        return None
    if h.startswith("/"):
        return posixpath.normpath(h.lstrip("/"))
    if base_dir:
        return posixpath.normpath(posixpath.join(base_dir, h))
    return posixpath.normpath(h)


def _li_target(li, base_dir):
    for a in li.iter():
        if localname(a.tag) == "a":
            href = a.get("href")
            if href:
                return resolve_nav_href(href, base_dir)
    return None


def _navpoint_target(np_el, base_dir):
    for c in np_el.iter():
        if localname(c.tag) == "content":
            return resolve_nav_href(c.get("src") or "", base_dir)
    return None


def reorder_xhtml_nav(root, base_dir, spine_index, removed_paths, stats):
    """重排 nav.xhtml 中的目录列表，返回是否有改动。"""
    changed = False
    for nav_el in root.iter():
        if localname(nav_el.tag) != "nav":
            continue
        nav_type = (nav_el.get("{%s}type" % EPUB_OPS_NS)
                    or nav_el.get("type") or "").lower()
        if "landmarks" in nav_type or "page-list" in nav_type:
            continue
        if "toc" not in nav_type and not _nav_looks_like_toc(nav_el, base_dir, spine_index):
            continue
        if _reorder_nav_element(nav_el, base_dir, spine_index, removed_paths, stats):
            changed = True
    return changed


def _nav_looks_like_toc(nav_el, base_dir, spine_index):
    matched = 0
    for a in nav_el.iter():
        if localname(a.tag) == "a":
            if resolve_nav_href(a.get("href") or "", base_dir) in spine_index:
                matched += 1
    return matched >= 2


def _reorder_nav_element(nav_el, base_dir, spine_index, removed_paths, stats):
    changed = False
    for sub in list(nav_el):
        if localname(sub.tag) == "ol":
            if _reorder_ol(sub, base_dir, spine_index, removed_paths, stats):
                changed = True
    return changed


def _reorder_ol(ol, base_dir, spine_index, removed_paths, stats):
    """按 spine 顺序重排一个 ol 下的 li；返回是否有改动。"""
    changed = False
    children = list(ol)
    to_remove = []
    kept = []
    for c in children:
        if localname(c.tag) != "li":
            continue
        target = _li_target(c, base_dir)
        if target in removed_paths:
            to_remove.append(c)
            stats.navpoints_removed += 1
            changed = True
            continue
        si = spine_index.get(target)
        kept.append((si if si is not None else BIG, c))
    for c in to_remove:
        remove_element(ol, c)
    if [c for _, c in kept] != [c for _, c in sorted(kept, key=lambda t: t[0])]:
        changed = True
    kept.sort(key=lambda t: t[0])
    for c in children:
        if c in to_remove:
            continue
        ol.remove(c)
    for _, c in kept:
        ol.append(c)
    for c in children:
        if localname(c.tag) != "li" and c not in to_remove:
            ol.append(c)
    for _, c in kept:
        for sub in c:
            if localname(sub.tag) == "ol":
                if _reorder_ol(sub, base_dir, spine_index, removed_paths, stats):
                    changed = True
    return changed


def reorder_ncx(root, base_dir, spine_index, removed_paths, stats):
    changed = False
    for navmap in root.iter():
        if localname(navmap.tag) != "navMap":
            continue
        if _reorder_navmap(navmap, base_dir, spine_index, removed_paths, stats):
            changed = True
    if changed:
        _renumber_play_order(root)
    return changed


def _reorder_navmap(navmap, base_dir, spine_index, removed_paths, stats):
    changed = False
    children = list(navmap)
    to_remove = []
    kept = []
    for c in children:
        if localname(c.tag) != "navPoint":
            continue
        target = _navpoint_target(c, base_dir)
        if target in removed_paths:
            to_remove.append(c)
            stats.navpoints_removed += 1
            changed = True
            continue
        si = spine_index.get(target)
        kept.append((si if si is not None else BIG, c))
    for c in to_remove:
        remove_element(navmap, c)
    if [c for _, c in kept] != [c for _, c in sorted(kept, key=lambda t: t[0])]:
        changed = True
    kept.sort(key=lambda t: t[0])
    for c in children:
        if c in to_remove:
            continue
        navmap.remove(c)
    for _, c in kept:
        navmap.append(c)
    for c in children:
        if localname(c.tag) != "navPoint" and c not in to_remove:
            navmap.append(c)
    for _, c in kept:
        if _reorder_navmap(c, base_dir, spine_index, removed_paths, stats):
            changed = True
    return changed


def _renumber_play_order(root):
    counter = [0]

    def walk(el):
        for child in el:
            if localname(child.tag) == "navPoint":
                counter[0] += 1
                child.set("playOrder", str(counter[0]))
                walk(child)

    for navmap in root.iter():
        if localname(navmap.tag) == "navMap":
            walk(navmap)


# --------------------------------------------------------------------------
# EPUB 容器
# --------------------------------------------------------------------------

class EpubFile:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise EpubError("文件不存在: %s" % path)
        try:
            self.zf = zipfile.ZipFile(self.path, "r")
        except zipfile.BadZipFile:
            raise EpubError("不是有效的 EPUB（ZIP 结构损坏）: %s" % path)
        self.names = self.zf.namelist()
        self.opf_path = self._find_opf()
        if not self.opf_path:
            raise EpubError("不是有效的 EPUB（缺少 META-INF/container.xml 或 .opf）")
        self.opf_root = None
        self.manifest = {}
        self.spine_ids = []
        self._parse_opf()

    def _find_opf(self):
        root, _, _, err, _ = read_xml_doc(self.zf, "META-INF/container.xml")
        if root is not None:
            for el in root.iter():
                if localname(el.tag) == "rootfile":
                    p = el.get("full-path")
                    if p and p in self.names:
                        return p
        for name in self.names:
            if name.lower().endswith(".opf"):
                return name
        return None

    def _parse_opf(self):
        root, enc, bom, err, _ = read_xml_doc(self.zf, self.opf_path)
        if root is None:
            raise EpubError("OPF 解析失败（%s）：%s" % (self.opf_path, err))
        self.opf_root, self.opf_enc, self.opf_bom = root, enc, bom
        self.opf_base = posixpath.dirname(self.opf_path)
        manifest_el = spine_el = metadata_el = None
        for child in root:
            ln = localname(child.tag)
            if ln == "manifest":
                manifest_el = child
            elif ln == "spine":
                spine_el = child
            elif ln == "metadata":
                metadata_el = child
        self.manifest_el, self.spine_el, self.metadata_el = manifest_el, spine_el, metadata_el
        if manifest_el is not None:
            for item in manifest_el:
                if localname(item.tag) != "item":
                    continue
                iid = item.get("id")
                href = item.get("href")
                if not iid or not href:
                    continue
                self.manifest[iid] = {
                    "element": item,
                    "id": iid,
                    "href": href,
                    "media_type": item.get("media-type") or "",
                    "properties": (item.get("properties") or "").split(),
                    "path": self.resolve_href(href),
                }
        if spine_el is not None:
            for ir in spine_el:
                if localname(ir.tag) == "itemref":
                    idref = ir.get("idref")
                    if idref:
                        self.spine_ids.append(idref)
        if not self.spine_ids:
            raise EpubError("OPF 中没有 spine 阅读顺序，无法处理")

    def resolve_href(self, href):
        h = unquote((href or "").split("#", 1)[0].strip())
        if not h or _URL_SCHEME_RE.match(h):
            return None
        if h.startswith("/"):
            return posixpath.normpath(h.lstrip("/"))
        if self.opf_base:
            return posixpath.normpath(posixpath.join(self.opf_base, h))
        return posixpath.normpath(h)

    def find_nav_docs(self):
        """返回需要重排的导航文档 zip 路径集合。"""
        nav_paths = set()
        for item in self.manifest.values():
            if not item["path"]:
                continue
            if "nav" in item["properties"]:
                nav_paths.add(item["path"])
                continue
            p = item["path"].lower()
            if p.endswith("nav.xhtml") or p.endswith("toc.ncx"):
                nav_paths.add(item["path"])
        for name in self.names:
            if name.lower().endswith(".ncx"):
                nav_paths.add(name)
        if self.spine_el is not None:
            toc_id = self.spine_el.get("toc")
            if toc_id and toc_id in self.manifest and self.manifest[toc_id]["path"]:
                nav_paths.add(self.manifest[toc_id]["path"])
        return nav_paths

    def close(self):
        self.zf.close()


# --------------------------------------------------------------------------
# 主处理流程
# --------------------------------------------------------------------------

def _default_output(input_path):
    p = Path(input_path)
    out = p.with_name(p.stem + "_cleaned.epub")
    n = 1
    while out.exists():
        out = p.with_name("%s_cleaned-%d.epub" % (p.stem, n))
        n += 1
    return out


def process(input_path, output_path, options):
    report = {
        "input": str(input_path),
        "output": str(output_path),
        "reorder": {},
        "clean": {},
        "nav": {},
        "verification": "not-run",
        "warnings": [],
    }
    epub = EpubFile(input_path)
    try:
        rules = (Rules.load(options.rules, use_text=not options.no_text_ads)
                 if options.rules else Rules.defaults(use_text=not options.no_text_ads))
        stats = CleanStats()
        doc_cache = {}

        def get_doc(name):
            if name not in doc_cache:
                doc_cache[name] = read_xml_doc(epub.zf, name)
            return doc_cache[name]

        # ---- 1. 提取 spine 各条目标题与章节编号 ----
        items = []
        for idx, idref in enumerate(epub.spine_ids):
            mitem = epub.manifest.get(idref)
            path = mitem["path"] if mitem else None
            title, vol, chap = "", None, None
            if path:
                root, enc, bom, err, raw = get_doc(path)
                if root is not None:
                    title = extract_title(root)
                else:
                    try:
                        title = extract_title_regex(raw.decode(enc, errors="replace"))
                    except Exception:  # noqa: BLE001
                        title = ""
                vol, chap = parse_numbering(title, posixpath.basename(path))
            else:
                report["warnings"].append(
                    "spine 中的 idref=%s 在 manifest 里不存在" % idref)
            items.append({"index": idx, "id": idref, "title": title,
                          "path": path, "vol": vol, "chap": chap})

        # ---- 2. 计算新顺序 ----
        if options.no_reorder:
            new_ids, reorder_info = None, {"performed": False, "reason": "skipped"}
        else:
            new_ids, reorder_info = compute_new_order(items)
        title_by_id = {it["id"]: it["title"] for it in items}
        if new_ids is not None and new_ids != list(epub.spine_ids):
            reorder_info["original_order"] = [title_by_id.get(i, "?") for i in epub.spine_ids]
            reorder_info["new_order"] = [title_by_id.get(i, "?") for i in new_ids]
        elif new_ids is not None:
            reorder_info["note"] = "顺序已经正确，无需调整"
        report["reorder"] = reorder_info

        # ---- 3. 清理所有 XHTML/HTML/NCX 文档 ----
        clean_targets = []
        for name in epub.names:
            if name.startswith("META-INF/") or name.endswith("/"):
                continue
            lower = name.lower()
            if lower.endswith((".xhtml", ".html", ".htm", ".ncx")):
                clean_targets.append(name)
        dirty = set()
        ad_page_candidates = {}
        parse_failures = 0
        for name in clean_targets:
            root, enc, bom, err, raw = get_doc(name)
            if root is None:
                parse_failures += 1
                continue
            text0 = "".join(root.itertext())
            if any(p.search(text0) for p in rules.text_patterns):
                ad_page_candidates[name] = len(text0)
            before = stats.snapshot()
            if name.lower().endswith(".ncx"):
                clean_ncx(root, rules, stats)
            else:
                clean_tree(root, None, rules, options.aggressive, stats)
            if stats.snapshot() != before:
                dirty.add(name)
                stats.files_modified += 1
        if parse_failures >= 2 and parse_failures * 2 >= len(clean_targets):
            raise EpubError(
                "大量文档解析失败（%d/%d），文件可能已 DRM 加密或不是标准 EPUB"
                % (parse_failures, len(clean_targets)))
        if parse_failures:
            report["warnings"].append(
                "%d 个文档无法按 XML 解析，已保持原样（多为非 XHTML 文件）"
                % parse_failures)
        if "META-INF/encryption.xml" in epub.names:
            report["warnings"].append(
                "检测到 META-INF/encryption.xml：字体混淆可忽略；若是 DRM 需先解密")

        # ---- 4. 纯广告页从 spine/manifest 移除（仅限本次清理后基本只剩广告残留的页）----
        # 判定：原文本命中广告规则；清理后无媒体；残留文本 <=50 字且被清掉的比例 >=75%。
        # 正常章节即使夹带广告，残留的正文通常也远大于此，不会被误删。
        original_spine_ids = list(epub.spine_ids)
        spine_paths = {epub.manifest[i]["path"] for i in original_spine_ids
                       if i in epub.manifest and epub.manifest[i]["path"]}
        emptied = set()
        for name in dirty:
            if name not in spine_paths:
                continue
            root = doc_cache[name][0]
            if root is None:
                continue
            if document_is_empty(root):
                emptied.add(name)
                continue
            orig_len = ad_page_candidates.get(name)
            if orig_len is None or orig_len < 20:
                continue
            remaining = len("".join(root.itertext()).strip())
            if remaining <= 50 and (orig_len - remaining) / orig_len >= 0.75:
                emptied.add(name)
        removed_ids = set()
        removed_paths = set()
        if emptied and len(emptied) < len(original_spine_ids):
            for idref in original_spine_ids:
                mitem = epub.manifest.get(idref)
                if mitem and mitem["path"] in emptied:
                    removed_ids.add(idref)
                    removed_paths.add(mitem["path"])
            for idref in removed_ids:
                if idref in epub.manifest:
                    remove_element(epub.manifest_el, epub.manifest[idref]["element"])
                    del epub.manifest[idref]
            report["warnings"].append(
                "已从阅读顺序移除 %d 个纯广告页" % len(removed_ids))

        # ---- 5. 重写 OPF（spine 顺序 + 元数据清理）----
        base_spine = new_ids if new_ids is not None else original_spine_ids
        final_spine = [i for i in base_spine if i in epub.manifest]
        if not final_spine:
            final_spine = original_spine_ids
        spine_changed = final_spine != original_spine_ids
        if spine_changed and epub.spine_el is not None:
            itemrefs = [c for c in epub.spine_el if localname(c.tag) == "itemref"]
            others = [c for c in epub.spine_el if localname(c.tag) != "itemref"]
            by_id = {ir.get("idref"): ir for ir in itemrefs}
            ordered = [by_id[i] for i in final_spine if i in by_id]
            for c in list(epub.spine_el):
                epub.spine_el.remove(c)
            for c in others + ordered:
                epub.spine_el.append(c)
            epub.spine_ids = final_spine
        meta_changed = clean_opf_metadata(epub.metadata_el, rules, stats)
        if spine_changed or meta_changed:
            stats.files_modified += 1
        opf_bytes = serialize_xml_doc(epub.opf_root, epub.opf_enc, epub.opf_bom)

        # ---- 6. 目录重排 ----
        spine_index = {}
        for i, idref in enumerate(final_spine):
            mitem = epub.manifest.get(idref)
            if mitem and mitem["path"]:
                spine_index[mitem["path"]] = i
        nav_entries_removed = 0
        for name in epub.find_nav_docs():
            if name not in doc_cache:
                continue
            root, enc, bom, err, raw = doc_cache[name]
            if root is None:
                continue
            base_dir = posixpath.dirname(name)
            before_nav = stats.navpoints_removed
            if name.lower().endswith(".ncx"):
                nav_changed = reorder_ncx(root, base_dir, spine_index,
                                          removed_paths, stats)
            else:
                nav_changed = reorder_xhtml_nav(root, base_dir, spine_index,
                                                removed_paths, stats)
            if nav_changed or stats.navpoints_removed != before_nav:
                dirty.add(name)
                stats.files_modified += 1
                nav_entries_removed += stats.navpoints_removed - before_nav
        report["nav"] = {"reordered": True, "entries_removed": nav_entries_removed}
        report["clean"] = stats.as_dict()

        # ---- 7. 组装输出 ----
        modified = {epub.opf_path: opf_bytes}
        for name in dirty:
            root, enc, bom, err, raw = doc_cache[name]
            if root is not None:
                modified[name] = serialize_xml_doc(root, enc, bom)
        if meta_changed and epub.opf_path not in dirty:
            dirty.add(epub.opf_path)

        if not options.dry_run:
            _write_output(epub, modified, output_path)
            report["verification"] = _verify_output(output_path, epub, final_spine)
        else:
            report["verification"] = "dry-run"
        return report
    finally:
        epub.close()


def _write_output(epub, modified, output_path):
    output_path = Path(output_path)
    if str(output_path.parent) and not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
    # 先把所有条目读入内存并关闭源 zip：Windows 上替换被打开的文件会失败
    payload = []
    for old in epub.zf.infolist():
        if old.filename == "mimetype":
            continue
        data = modified.get(old.filename)
        if data is None:
            data = epub.zf.read(old.filename)
        payload.append((old.filename, data, old.compress_type,
                        old.date_time, old.external_attr))
    try:
        mimetype = epub.zf.read("mimetype")
    except KeyError:
        mimetype = b"application/epub+zip"
    epub.zf.close()
    tmp = output_path.with_name(output_path.name + ".tmp")
    with zipfile.ZipFile(tmp, "w") as zout:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zout.writestr(info, mimetype)
        for name, data, comp, dt, attr in payload:
            info = zipfile.ZipInfo(name, date_time=dt)
            info.compress_type = comp
            info.external_attr = attr
            zout.writestr(info, data)
    tmp.replace(output_path)


def _verify_output(output_path, epub, final_spine):
    """输出完整性校验；失败则删除产物并抛出。"""
    try:
        with zipfile.ZipFile(output_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                raise EpubError("输出 ZIP 校验失败: %s" % bad)
            infos = zf.infolist()
            if not infos or infos[0].filename != "mimetype":
                raise EpubError("输出 EPUB 的 mimetype 不在首位")
            if infos[0].compress_type != zipfile.ZIP_STORED:
                raise EpubError("输出 EPUB 的 mimetype 必须为不压缩存储")
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                if name.lower().endswith((".xhtml", ".html", ".htm", ".opf", ".ncx")):
                    root, _, _, err, _ = read_xml_doc(zf, name)
                    if root is None:
                        raise EpubError("输出文档 XML 校验失败: %s（%s）" % (name, err))
            opf_name = None
            root, _, _, _, _ = read_xml_doc(zf, "META-INF/container.xml")
            if root is not None:
                for el in root.iter():
                    if localname(el.tag) == "rootfile":
                        opf_name = el.get("full-path")
                        break
            if opf_name is None:
                opf_name = epub.opf_path
            root, _, _, _, _ = read_xml_doc(zf, opf_name)
            if root is None:
                raise EpubError("输出 OPF 校验失败")
            spine_count = 0
            for sp in root.iter():
                if localname(sp.tag) == "spine":
                    spine_count = sum(1 for c in sp if localname(c.tag) == "itemref")
                    break
            if spine_count != len(final_spine):
                raise EpubError("输出 spine 条目数不一致: %d != %d"
                                % (spine_count, len(final_spine)))
        return "passed"
    except Exception:
        try:
            Path(output_path).unlink()
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="epub_reorder_clean",
        description="小说 EPUB 章节重排 + 广告网址清理（纯标准库）")
    p.add_argument("input", help="输入的 .epub 文件路径")
    p.add_argument("-o", "--output", help="输出路径（默认 <书名>_cleaned.epub）")
    p.add_argument("--in-place", action="store_true",
                   help="原地修改（先把原文件备份为 .bak）")
    p.add_argument("--dry-run", action="store_true", help="只分析，不写输出文件")
    p.add_argument("--no-reorder", action="store_true", help="只清理广告，不重排章节")
    p.add_argument("--no-clean", action="store_true", help="只重排章节，不清理广告")
    p.add_argument("--no-text-ads", action="store_true",
                   help="只删除广告网址/链接，保留推广文字")
    p.add_argument("--aggressive", action="store_true",
                   help="删除正文中所有裸网址（默认只删疑似广告网址）")
    p.add_argument("--rules", help="自定义广告规则 JSON 文件路径")
    p.add_argument("--report", help="把 JSON 处理报告写入指定路径")
    p.add_argument("--quiet", action="store_true", help="减少终端输出")
    p.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    return p


def print_summary(report, quiet=False):
    r = report["reorder"]
    lines = []
    lines.append("输入: %s" % report["input"])
    lines.append("输出: %s" % report["output"])
    if r.get("performed"):
        if r.get("note"):
            lines.append("章节顺序: %s" % r["note"])
        else:
            lines.append("章节顺序: 已重排（编号章节 %d / 共 %d）"
                         % (r.get("numbered", 0), r.get("total", 0)))
            old = r.get("original_order") or []
            new = r.get("new_order") or []
            shown = 0
            for i, (a, b) in enumerate(zip(old, new)):
                if a != b and shown < 8:
                    lines.append("  第%2d章: %s  ->  %s" % (i + 1, a or "?", b or "?"))
                    shown += 1
    else:
        reason = {
            "no-chapter-numbers": "未识别到章节编号，跳过重排",
            "insufficient-chapter-numbers": "编号章节过少，跳过重排",
            "skipped": "按参数要求跳过重排",
        }.get(r.get("reason"), r.get("reason", ""))
        lines.append("章节顺序: %s" % reason)
    c = report.get("clean") or {}
    if c:
        parts = []
        if c.get("links_removed"):
            parts.append("广告链接 %d" % c["links_removed"])
        if c.get("urls_removed"):
            parts.append("正文网址 %d" % c["urls_removed"])
        if c.get("text_ads_removed"):
            parts.append("推广文字 %d" % c["text_ads_removed"])
        if c.get("images_removed"):
            parts.append("广告图 %d" % c["images_removed"])
        if c.get("elements_removed"):
            parts.append("冗余元素 %d" % c["elements_removed"])
        if c.get("metadata_fields_removed"):
            parts.append("元数据字段 %d" % c["metadata_fields_removed"])
        lines.append("广告清理: %s" % ("、".join(parts) if parts else "未发现广告内容"))
        lines.append("改动文档: %d 个" % c.get("files_modified", 0))
    nav = report.get("nav") or {}
    if nav.get("entries_removed"):
        lines.append("目录清理: 移除 %d 个广告目录项" % nav["entries_removed"])
    lines.append("完整性校验: %s" % report.get("verification", "not-run"))
    for w in report.get("warnings") or []:
        lines.append("注意: %s" % w)
    print("\n".join(lines))


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.no_reorder and args.no_clean:
        print("错误: --no-reorder 与 --no-clean 不能同时使用", file=sys.stderr)
        return 2
    if args.in_place and args.output:
        print("错误: --in-place 与 -o 不能同时使用", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if args.in_place:
        backup = input_path.with_name(input_path.name + ".bak")
        n = 1
        while backup.exists():
            backup = input_path.with_name("%s.bak-%d" % (input_path.name, n))
            n += 1
        try:
            shutil.copy2(str(input_path), str(backup))
        except OSError as exc:
            print("错误: 无法创建备份 %s: %s" % (backup, exc), file=sys.stderr)
            return 1
        output_path = input_path
    else:
        output_path = Path(args.output) if args.output else _default_output(input_path)

    try:
        report = process(input_path, output_path, args)
    except EpubError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print("未预期的错误: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 1

    if not args.quiet:
        print_summary(report)
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.quiet:
            print("报告已写入: %s" % args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

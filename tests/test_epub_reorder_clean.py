#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 epub_reorder_clean.py 做端到端断言测试。"""
import json
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPT = TESTS.parent / "rerange" / "scripts" / "epub_reorder_clean.py"
PY = sys.executable

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print("  PASS  %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def run(args):
    return subprocess.run([PY, str(SCRIPT)] + args, capture_output=True, text=True)


def local(tag):
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def read_auto(zf, name):
    """按文件自声明编码解码（测试书含 GBK 章节）。"""
    import re as _re
    raw = zf.read(name)
    m = _re.search(rb'encoding=["\']([\w\-]+)["\']', raw[:256])
    if m:
        enc = m.group(1).decode("ascii", "replace")
    else:
        enc = "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        return raw.decode("gb18030", errors="replace")


def spine_titles(epub_path):
    with zipfile.ZipFile(epub_path) as zf:
        root = ET.fromstring(read_auto(zf, "OEBPS/content.opf"))
        items = {}
        spine = []
        for el in root.iter():
            ln = local(el.tag)
            if ln == "item":
                items[el.get("id")] = el.get("href")
            elif ln == "itemref":
                spine.append(el.get("idref"))
        titles = []
        for idref in spine:
            href = items.get(idref)
            if href is None:
                titles.append("MISSING:" + str(idref))
                continue
            doc = ET.fromstring(read_auto(zf, "OEBPS/" + href))
            title = ""
            for el in doc.iter():
                if local(el.tag) in ("h1", "h2", "h3"):
                    title = "".join(el.itertext()).strip()
                    break
            titles.append(title)
        return titles


def nav_titles(epub_path, nav_name="OEBPS/nav.xhtml"):
    with zipfile.ZipFile(epub_path) as zf:
        doc = ET.fromstring(read_auto(zf, nav_name))
        out = []
        for a in doc.iter():
            if local(a.tag) == "a":
                t = "".join(a.itertext()).strip()
                if t:
                    out.append(t)
        return out


def all_text(epub_path):
    chunks = []
    with zipfile.ZipFile(epub_path) as zf:
        for name in zf.namelist():
            if name.lower().endswith((".xhtml", ".opf", ".ncx")):
                chunks.append(read_auto(zf, name))
    return "\n".join(chunks)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="epub_test_"))
    print("workdir:", tmp)
    sys.path.insert(0, str(TESTS))
    import make_test_epubs as gen
    gen.build_shuffled(str(tmp / "shuffled.epub"))
    gen.build_ordered(str(tmp / "ordered.epub"))
    gen.build_unnumbered(str(tmp / "unnumbered.epub"))

    # ---------- 用例 1：乱序 + 广告 ----------
    print("\n[1] shuffled.epub 重排 + 广告清理")
    out = tmp / "shuffled_cleaned.epub"
    r = run([str(tmp / "shuffled.epub"), "-o", str(out), "--report", str(tmp / "r1.json")])
    print(r.stdout.strip())
    check("exit=0", r.returncode == 0, r.stderr)
    check("output exists", out.exists())
    report = json.loads((tmp / "r1.json").read_text(encoding="utf-8"))

    titles = spine_titles(out)
    expect = ["序章 命运的起点", "第一章 开始", "第二章 风波", "第三章 转折",
              "第四章 暗流", "第五章 高潮", "番外一 后来的事"]
    check("spine 重排正确（含前置/后记归位、广告页移除）", titles == expect,
          "got %s" % titles)

    text = all_text(out)
    check("广告站点域名已清除", "biquge" not in text.lower(), text[:500])
    check("短链接已清除", "t.cn" not in text)
    check("推广文字已清除", "本书由" not in text and "无弹窗" not in text)
    check("正文内容保留", "第一章的正文内容" in text)
    check("实体符号正常保留", "内容" in text)
    check("GBK 章节内容保留", "第二章的正文" in text)
    check("站内链接保留", "返回上一章" in text)
    check("元数据广告来源已清除", "dc:source" not in text)
    check("验证通过", report["verification"] == "passed")

    nav = nav_titles(out)
    check("nav.xhtml 目录顺序与 spine 一致",
          nav == [t for t in titles], "nav=%s" % nav)

    # mimetype 首位且不压缩
    with zipfile.ZipFile(out) as zf:
        infos = zf.infolist()
        check("mimetype 首位且 STORED",
              infos[0].filename == "mimetype" and infos[0].compress_type == zipfile.ZIP_STORED)

    # 幂等性：再跑一次应无变化
    out2 = tmp / "shuffled_cleaned2.epub"
    r2 = run([str(out), "-o", str(out2), "--report", str(tmp / "r2.json")])
    rep2 = json.loads((tmp / "r2.json").read_text(encoding="utf-8"))
    check("二次运行顺序已正确", rep2["reorder"].get("note") == "顺序已经正确，无需调整",
          str(rep2["reorder"]))
    clean2 = rep2.get("clean") or {}
    total_ads = sum(v for k, v in clean2.items() if k != "files_modified")
    check("二次运行无广告可清理", total_ads == 0, str(clean2))

    # ---------- 用例 2：顺序正确无广告 ----------
    print("\n[2] ordered.epub 顺序正确 + 无广告")
    out3 = tmp / "ordered_cleaned.epub"
    r3 = run([str(tmp / "ordered.epub"), "-o", str(out3), "--report", str(tmp / "r3.json")])
    check("exit=0", r3.returncode == 0, r3.stderr)
    rep3 = json.loads((tmp / "r3.json").read_text(encoding="utf-8"))
    check("无需重排", rep3["reorder"].get("note") == "顺序已经正确，无需调整")
    clean3 = rep3.get("clean") or {}
    total3 = sum(v for k, v in clean3.items() if k != "files_modified")
    check("无广告可清理", total3 == 0, str(clean3))
    check("正文完整", "正文二" in all_text(out3))

    # ---------- 用例 3：无编号章节 ----------
    print("\n[3] unnumbered.epub 无章节编号")
    out4 = tmp / "unnumbered_cleaned.epub"
    r4 = run([str(tmp / "unnumbered.epub"), "-o", str(out4), "--report", str(tmp / "r4.json")])
    check("exit=0", r4.returncode == 0, r4.stderr)
    rep4 = json.loads((tmp / "r4.json").read_text(encoding="utf-8"))
    check("重排被跳过", rep4["reorder"].get("reason") == "no-chapter-numbers",
          str(rep4["reorder"]))
    clean4 = rep4.get("clean") or {}
    check("广告仍被清理", clean4.get("links_removed", 0) >= 1, str(clean4))
    check("原顺序保留", spine_titles(out4) == ["风雪夜归人", "故人重逢", "决战前夕"])

    # ---------- 用例 4：dry-run 与非法输入 ----------
    print("\n[4] dry-run / 非法输入")
    out5 = tmp / "never_written.epub"
    r5 = run([str(tmp / "shuffled.epub"), "-o", str(out5), "--dry-run", "--quiet"])
    check("dry-run 不写文件", r5.returncode == 0 and not out5.exists(), r5.stderr)
    bad = tmp / "bad.epub"
    bad.write_bytes(b"not a zip at all")
    r6 = run([str(bad)])
    check("非法 EPUB 报错 exit=1", r6.returncode == 1 and "错误" in (r6.stderr + r6.stdout))

    # ---------- 用例 5：in-place 备份 ----------
    print("\n[5] --in-place 备份")
    import shutil
    src = tmp / "inplace.epub"
    shutil.copy(str(tmp / "shuffled.epub"), str(src))
    r7 = run([str(src), "--in-place", "--quiet"])
    check("in-place exit=0", r7.returncode == 0, r7.stderr)
    check("备份文件存在", (tmp / "inplace.epub.bak").exists())
    check("原文件已被清理版替换",
          "biquge" not in all_text(src).lower())

    # ---------- 用例 6：--rules 自定义规则 ----------
    print("\n[6] --rules 自定义规则")
    rules_file = tmp / "rules.json"
    rules_file.write_text(json.dumps({
        "mode": "merge",
        "text_patterns": [r"正文一"]
    }, ensure_ascii=False), encoding="utf-8")
    out8 = tmp / "rules_cleaned.epub"
    r8 = run([str(tmp / "unnumbered.epub"), "-o", str(out8), "--rules", str(rules_file), "--quiet"])
    check("自定义规则 exit=0", r8.returncode == 0, r8.stderr)
    check("自定义规则生效（'正文一' 被删）", "正文一" not in all_text(out8))

    print("\n===== 结果: %d 通过, %d 失败 =====" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("失败项:", FAILED)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

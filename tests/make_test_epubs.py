#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成用于测试的小说 EPUB：乱序章节 + 广告内容。"""
import os
import sys
import zipfile

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def xhtml(title, body, encoding="utf-8", extra_head=""):
    if encoding.lower() in ("utf-8", "utf8"):
        decl = '<?xml version="1.0" encoding="UTF-8"?>'
    else:
        decl = '<?xml version="1.0" encoding="%s"?>' % encoding
    html = """%s
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>%s</title>%s</head>
<body>
<h1>%s</h1>
%s
</body>
</html>
""" % (decl, title, extra_head, title, body)
    return html.encode(encoding, errors="xmlcharrefreplace")


def build_shuffled(path):
    """章节乱序 + 各类广告 + 纯广告页 + GBK 文件 + 实体符号。"""
    chapters = [
        # (id, 文件名, 标题, 正文, 编码)
        ("prologue", "prologue.xhtml", "序章 命运的起点",
         "<p>这是序章的正文，讲述故事的开端。</p>"
         "<p>苍茫大山之中，少年背着药篓一步步往山下走，夕阳将他的影子拉得很长。</p>", "utf-8"),
        ("c1", "chap1.xhtml", "第一章 开始",
         "<p>第一章的正文内容，一切从这里开始。</p>"
         "<p>他紧了紧拳头，望着远处的山峦，心中暗暗发誓，定要走出这片大山，去看一看外面的世界。</p>"
         "<p>本书由小小书虫整理提供，更多好书请访问本站。</p>"
         "<p>请记住本站网址：www.biquge.com 下次再来</p>"
         "<p><a href=\"http://www.biquge.com/bqg/123\">笔趣阁</a>广告链接</p>"
         "<p>读者群：123456789 欢迎加入讨论</p>", "utf-8"),
        ("c2", "chap2.xhtml", "第二章 风波",
         "<p>第二章的正文&nbsp;内容&mdash;包含实体符号。</p>"
         "<p>山路崎岖，雨后的泥地格外湿滑，他深一脚浅一脚地往镇上赶去。</p>"
         "<div class=\"ad banner\"><a href=\"http://t.cn/RxAbCdEf\">短链接推广</a></div>"
         "<img src=\"http://ads.example.com/banner.gif\" alt=\"ad\"/>"
         "<p><a href=\"chap1.xhtml#sec\">返回上一章</a>继续阅读。</p>", "gbk"),
        ("c3", "chap3.xhtml", "第三章 转折",
         "<p>第三章正文。</p>"
         "<p>镇口的老槐树下围了一圈人，中间站着一位身穿青衫的中年人，正在摇头叹息。</p>"
         "<p>手机版阅读请访问 m.biquge.com</p>", "utf-8"),
        ("c4", "chap4.xhtml", "第四章 暗流",
         "<p>第四章正文。</p>"
         "<p>夜深人静，客栈的灯笼在风里摇晃，他推开窗，看见街角有一道黑影一闪而过。</p>", "utf-8"),
        ("c5", "chap5.xhtml", "第五章 高潮",
         "<p>第五章正文。</p>"
         "<p>锣鼓喧天，擂台之上尘土飞扬，两人你来我往，转眼已过了三十余招。</p>"
         "<p>关注微信公众号：测试小说推荐</p>", "utf-8"),
        ("extra", "extra.xhtml", "番外一 后来的事",
         "<p>番外篇正文。</p>"
         "<p>多年以后，他再次回到这座大山，山还是那座山，人却已不再是当年的人。</p>", "utf-8"),
        ("adpage", "adpage.xhtml", "本站广告",
         "<p>本站推荐以下好书：<a href=\"http://www.biquge.com/\">笔趣阁</a></p>"
         "<p>无弹窗无广告全文阅读，请访问 www.biquge.com</p>", "utf-8"),
    ]
    # 乱序：把 5 放最前，4 放中间，广告页混入
    spine_order = ["c5", "c1", "prologue", "c3", "adpage", "c2", "c4", "extra"]

    manifest = ['<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
    for cid, fname, *_rest in chapters:
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (cid, fname))
    spine = ['<itemref idref="%s"/>' % cid for cid in spine_order]
    navpoints = []
    for i, cid in enumerate(spine_order):
        fname = dict((c[0], c[1]) for c in chapters)[cid]
        title = dict((c[0], c[2]) for c in chapters)[cid]
        navpoints.append(
            '<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
            '<content src="%s"/></navPoint>' % (i, i + 1, title, fname))

    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>测试小说</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="bookid">urn:uuid:test-shuffled-1234</dc:identifier>
    <dc:source>https://www.biquge.com/book/1/</dc:source>
  </metadata>
  <manifest>
    %s
  </manifest>
  <spine toc="ncx">
    %s
  </spine>
</package>
""" % ("\n    ".join(manifest), "\n    ".join(spine))

    ncx = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:test-shuffled-1234"/></head>
  <docTitle><text>测试小说</text></docTitle>
  <navMap>
    %s
  </navMap>
</ncx>
""" % "\n    ".join(navpoints)

    nav = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>目录</title></head>
<body>
<nav epub:type="toc" id="toc">
<ol>
%s
</ol>
</nav>
</body>
</html>
""" % "\n".join(
        '  <li><a href="%s">%s</a></li>' % (
            dict((c[0], c[1]) for c in chapters)[cid],
            dict((c[0], c[2]) for c in chapters)[cid])
        for cid in spine_order)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        zf.writestr("OEBPS/nav.xhtml", nav)
        for cid, fname, title, body, enc in chapters:
            zf.writestr("OEBPS/" + fname, xhtml(title, body, enc))


def build_ordered(path):
    """章节顺序正确、无广告。"""
    chapters = [
        ("c1", "chap1.xhtml", "第一章 甲", "<p>正文一。</p>"),
        ("c2", "chap2.xhtml", "第二章 乙", "<p>正文二。</p>"),
        ("c3", "chap3.xhtml", "第三章 丙", "<p>正文三。</p>"),
    ]
    manifest = ['<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>']
    for cid, fname, *_ in chapters:
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (cid, fname))
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>顺序正确的小说</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="bookid">urn:uuid:test-ordered-5678</dc:identifier>
  </metadata>
  <manifest>
    %s
  </manifest>
  <spine toc="ncx">
    <itemref idref="c1"/><itemref idref="c2"/><itemref idref="c3"/>
  </spine>
</package>
""" % "\n    ".join(manifest)
    ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:test-ordered-5678"/></head>
  <docTitle><text>顺序正确的小说</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1"><navLabel><text>第一章 甲</text></navLabel><content src="chap1.xhtml"/></navPoint>
    <navPoint id="np2" playOrder="2"><navLabel><text>第二章 乙</text></navLabel><content src="chap2.xhtml"/></navPoint>
    <navPoint id="np3" playOrder="3"><navLabel><text>第三章 丙</text></navLabel><content src="chap3.xhtml"/></navPoint>
  </navMap>
</ncx>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        for cid, fname, title, body in chapters:
            zf.writestr("OEBPS/" + fname, xhtml(title, body))


def build_unnumbered(path):
    """章节标题无编号（重排应跳过），但含广告（应清理）。"""
    chapters = [
        ("c1", "a.xhtml", "风雪夜归人", "<p>正文一。</p><p>本站由书友整理：<a href=\"http://t.cn/xyz\">点我</a></p>"),
        ("c2", "b.xhtml", "故人重逢", "<p>正文二。</p>"),
        ("c3", "c.xhtml", "决战前夕", "<p>正文三。</p>"),
    ]
    manifest = ['<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>']
    for cid, fname, *_ in chapters:
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (cid, fname))
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>无编号小说</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="bookid">urn:uuid:test-unnum-9012</dc:identifier>
  </metadata>
  <manifest>
    %s
  </manifest>
  <spine toc="ncx">
    <itemref idref="c1"/><itemref idref="c2"/><itemref idref="c3"/>
  </spine>
</package>
""" % "\n    ".join(manifest)
    ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:test-unnum-9012"/></head>
  <docTitle><text>无编号小说</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1"><navLabel><text>风雪夜归人</text></navLabel><content src="a.xhtml"/></navPoint>
    <navPoint id="np2" playOrder="2"><navLabel><text>故人重逢</text></navLabel><content src="b.xhtml"/></navPoint>
    <navPoint id="np3" playOrder="3"><navLabel><text>决战前夕</text></navLabel><content src="c.xhtml"/></navPoint>
  </navMap>
</ncx>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip",
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        for cid, fname, title, body in chapters:
            zf.writestr("OEBPS/" + fname, xhtml(title, body))


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    build_shuffled(os.path.join(outdir, "shuffled.epub"))
    build_ordered(os.path.join(outdir, "ordered.epub"))
    build_unnumbered(os.path.join(outdir, "unnumbered.epub"))
    print("built: shuffled.epub ordered.epub unnumbered.epub in", outdir)

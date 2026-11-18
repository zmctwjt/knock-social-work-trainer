# -*- coding: utf-8 -*-
"""Markdown -> DOCX 构建器（毕业设计文档专用）

用法:
    python build_docx.py [--docs DIR] [--out FILE]

特性:
  * 封面 + 摘要/Abstract + 自动目录域 + 正文（3 节，罗马/阿拉伯页码）
  * 黑体三级标题、宋体小四正文、1.5 倍行距、首行缩进 2 字符
  * GFM 管道表 -> 三线表（表题可在表上或表下，统一提到表上）
  * 围栏代码块、引用块、列表、任务清单、行内粗体/行内代码
  * 图片 15cm 居中 + 图注；缺图灰框告警
  * 幂等重跑；构建后自检
"""
from __future__ import os
import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Emu

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "deliverables" / "docs"
OUT = ROOT / "deliverables" / "叩门AI陪练舱_生产化改造与重构方案.docx"

TEXT_W_CM = 21.0 - 3.17 * 2          # 14.66cm 版心宽度
BODY_PT = 12
CODE_PT = 8.5                        # 代码块字号（9pt→8.5pt，长行少折一行）
SHORT_LABELS = set("必填 密级 序号 等级 优先级 编号 组 类别 状态 阶段 周次 人天 "
                   "概率 类型 权重 占比 数量 次数 单位 端口 版本 环境 角色 "
                   "责任人 负责人 风险等级 是否 提示 结论".split())
SONG, HEI, MONO = "宋体", "黑体", "Consolas"
BLACK = RGBColor(0, 0, 0)
GRAY_TXT = RGBColor(0x59, 0x59, 0x59)
RED = RGBColor(0xC0, 0x00, 0x00)

SKIP_FILES = {"FACTS.md", "OUTLINE.md", "STYLE.md"}

TITLE = "叩门 · 社工个案面谈 AI 陪练舱"
SHORT_TITLE = "叩门 AI 陪练舱 · 生产化改造与重构方案"


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def set_run_font(run, ascii_font=SONG, ea_font=SONG, size=None, bold=None, color=None):
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    run.font.name = ascii_font
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), ascii_font)
    rFonts.set(qn("w:hAnsi"), ascii_font)
    rFonts.set(qn("w:eastAsia"), ea_font)


def set_first_line_chars(p, chars=200, size_pt=BODY_PT):
    """真正的中文『首行缩进 N 字符』：写 firstLineChars，同时给出 twips 兼容值。"""
    pPr = p._p.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        pPr.insert_element_before(ind, *PPR_TAIL)
    ind.set(qn("w:firstLineChars"), str(chars))
    ind.set(qn("w:firstLine"), str(int(size_pt * 20 * chars / 100)))


PPR_TAIL = ("w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
            "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
            "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
            "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
            "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
            "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr")


def ppr_add(pPr, el):
    pPr.insert_element_before(el, *PPR_TAIL)


def shade(element, fill):
    pPr = element.get_or_add_pPr() if hasattr(element, "get_or_add_pPr") else element
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr_add(pPr, shd)


def para_shade(p, fill):
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr_add(pPr, shd)


def add_left_bar(p, color="BFBFBF", sz=18):
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(sz))
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), color)
    bdr.append(left)
    pPr.insert_element_before(bdr, "w:shd", *PPR_TAIL)


def add_field(paragraph, instr, placeholder="1", size=9, bold=False):
    def _run():
        r = paragraph.add_run()
        set_run_font(r, SONG, SONG, size=size, bold=bold)
        return r

    r = _run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "begin")
    r._r.append(fc)

    r = _run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = instr
    r._r.append(it)

    r = _run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "separate")
    r._r.append(fc)

    r = paragraph.add_run(placeholder)
    set_run_font(r, SONG, SONG, size=size, bold=bold)

    r = _run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "end")
    r._r.append(fc)


# --------------------------------------------------------------------------
# Markdown 解析
# --------------------------------------------------------------------------
RE_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
RE_IMG = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")
RE_CAP = re.compile(r"^\*\*(表|图)\s*[0-9A-Za-z]+[-\u2013\u2014]\d+\s*.*\*\*$")
RE_UL = re.compile(r"^(\s*)[-*+]\s+(.*)$")
RE_OL = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
RE_TASK = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s*(.*)$")
RE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
RE_TBLCAP = re.compile(r"^\*\*(表)\s*[0-9A-Za-z]+[-\u2013\u2014]\d+.*\*\*$")


def is_cjk(ch):
    return "\u4e00" <= ch <= "\u9fff" or ch in "，。；：！？（）【】《》、·—“”‘’"


def smart_join(a, b):
    if not a:
        return b
    if not b:
        return a
    if is_cjk(a[-1]) or is_cjk(b[0]):
        return a + b
    if a[-1].isspace() or b[0].isspace():
        return a + b
    return a + " " + b


def split_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, buf, in_code = [], [], False
    for ch in s:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def parse_markdown(text, source=""):
    lines = text.split("\n")
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue

        # 围栏代码
        if s.startswith("```"):
            lang = s[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append({"t": "code", "lang": lang, "lines": buf})
            continue

        # 图片
        m = RE_IMG.match(s)
        if m:
            blocks.append({"t": "image", "alt": m.group(1).strip(), "src": m.group(2).strip()})
            i += 1
            continue

        # 表格
        if s.startswith("|") and i + 1 < n and RE_SEP.match(lines[i + 1].strip()):
            header = split_table_row(lines[i])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            blocks.append({"t": "table", "header": header, "rows": rows, "caption": None})
            continue

        # 标题
        m = RE_HEAD.match(s)
        if m:
            blocks.append({"t": "h", "level": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue

        # 分隔线
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            blocks.append({"t": "hr"})
            i += 1
            continue

        # 引用
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            blocks.append({"t": "quote", "text": " ".join(x for x in buf if x)})
            continue

        # 任务清单
        m = RE_TASK.match(line)
        if m:
            blocks.append({"t": "task", "indent": len(m.group(1)),
                           "checked": m.group(2).lower() == "x", "text": m.group(3).strip()})
            i += 1
            continue

        # 无序 / 有序列表
        m = RE_UL.match(line)
        if m:
            blocks.append({"t": "ul", "indent": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue
        m = RE_OL.match(line)
        if m:
            blocks.append({"t": "ol", "indent": len(m.group(1)),
                           "num": int(m.group(2)), "text": m.group(3).strip()})
            i += 1
            continue

        # 普通段落（连续非特殊行合并）
        buf = [s]
        i += 1
        while i < n:
            nx = lines[i]
            ns = nx.strip()
            if (not ns or ns.startswith(("#", "|", "```", ">", "![", "---"))
                    or RE_UL.match(nx) or RE_OL.match(nx)):
                break
            buf.append(ns)
            i += 1
        text_p = buf[0]
        for x in buf[1:]:
            text_p = smart_join(text_p, x)
        blocks.append({"t": "p", "text": text_p})

    return blocks


def attach_captions(blocks):
    """把紧贴表格的『表 x-y』题注统一提到表格上方。"""
    for idx, b in enumerate(blocks):
        if b.get("t") != "table":
            continue
        # 前置题注
        if idx > 0:
            prev = blocks[idx - 1]
            if prev.get("t") == "p" and RE_TBLCAP.match(prev["text"].strip()) and not b.get("caption"):
                b["caption"] = prev["text"].strip()
                blocks[idx - 1] = {"t": "consumed"}
        # 后置题注
        if not b.get("caption") and idx + 1 < len(blocks):
            nxt = blocks[idx + 1]
            if nxt.get("t") == "p" and RE_TBLCAP.match(nxt["text"].strip()):
                b["caption"] = nxt["text"].strip()
                blocks[idx + 1] = {"t": "consumed"}
    return [b for b in blocks if b.get("t") != "consumed"]


# --------------------------------------------------------------------------
# 行内格式
# --------------------------------------------------------------------------
INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*\n]+?\*|\[[^\]]+\]\([^)]+\))")


def add_inline(paragraph, text, size=BODY_PT, ascii_font=SONG, ea_font=SONG,
               bold_all=False, color=None):
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            r = paragraph.add_run(text[pos:m.start()])
            set_run_font(r, ascii_font, ea_font, size=size, bold=bold_all, color=color)
        tok = m.group(0)
        if tok.startswith("**"):
            r = paragraph.add_run(tok[2:-2])
            set_run_font(r, ascii_font, ea_font, size=size, bold=True, color=color)
        elif tok.startswith("`"):
            r = paragraph.add_run(tok[1:-1])
            set_run_font(r, "Consolas", SONG, size=(size - 1.5 if size >= 9 else size * 0.9),
                         bold=bold_all, color=color)
        elif tok.startswith("["):
            mm = re.match(r"\[([^\]]+)\]\(([^)]+)\)", tok)
            r = paragraph.add_run(mm.group(1))
            set_run_font(r, ascii_font, ea_font, size=size, bold=bold_all, color=color)
        else:  # *斜体*
            r = paragraph.add_run(tok[1:-1])
            set_run_font(r, ascii_font, ea_font, size=size, bold=bold_all, color=color)
            r.font.italic = True
        pos = m.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        set_run_font(r, ascii_font, ea_font, size=size, bold=bold_all, color=color)


# --------------------------------------------------------------------------
# 文档样式
# --------------------------------------------------------------------------
def setup_styles(doc):
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(BODY_PT)
    st.font.color.rgb = BLACK
    rPr = st.element.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.insert(0, rf)
    rf.set(qn("w:ascii"), "Times New Roman")
    rf.set(qn("w:hAnsi"), "Times New Roman")
    rf.set(qn("w:eastAsia"), SONG)
    pf = st.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    specs = {
        "Heading 1": (16, True, WD_ALIGN_PARAGRAPH.CENTER, 12, 12),
        "Heading 2": (14, True, WD_ALIGN_PARAGRAPH.LEFT, 12, 6),
        "Heading 3": (12, True, WD_ALIGN_PARAGRAPH.LEFT, 6, 6),
    }
    for name, (size, bold, align, sb, sa) in specs.items():
        s = doc.styles[name]
        s.font.name = "Times New Roman"
        s.font.size = Pt(size)
        s.font.bold = bold
        s.font.color.rgb = BLACK
        s.font.italic = False
        rPr = s.element.get_or_add_rPr()
        rf = rPr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rPr.insert(0, rf)
        rf.set(qn("w:ascii"), "Times New Roman")
        rf.set(qn("w:hAnsi"), "Times New Roman")
        rf.set(qn("w:eastAsia"), HEI)
        pf = s.paragraph_format
        pf.alignment = align
        pf.space_before = Pt(sb)
        pf.space_after = Pt(sa)
        pf.line_spacing = 1.5
        pf.keep_with_next = True
        pPr = s.element.get_or_add_pPr()
        ind = pPr.find(qn("w:ind"))
        if ind is not None:
            pPr.remove(ind)
    doc.styles["Heading 1"].paragraph_format.page_break_before = True

    # 目录样式：TOC 域条目自动套用 TOC 1/2/3
    # 注意：python-docx 默认模板里没有 TOC 1/2/3（Word 只在“更新域”时才创建），
    # 必须先 add_style 定义，否则目录条目沿用 Normal 的 1.5 倍行距 → 目录膨胀十几页。
    for lvl in (1, 2, 3):
        name = "TOC %d" % lvl
        try:
            st = doc.styles[name]
        except KeyError:
            st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            st.base_style = doc.styles["Normal"]
            st.quick_style = True
        # add_style 会写 w:customStyle="1"，Word 便不再把它当作内置的 TOC 1/2/3，
        # 生成的目录条目就不会套用这些格式 → 必须去掉该标记。
        cel = qn("w:customStyle")
        if cel in st.element.attrib:
            del st.element.attrib[cel]
        st.next_paragraph_style = doc.styles["Normal"]
        st.font.name = SONG
        st.font.size = Pt(12 if lvl == 1 else 10.5)
        st.font.bold = (lvl == 1)
        st.font.color.rgb = BLACK
        rpr = st.element.get_or_add_rPr()
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rpr.insert(0, rf)
        rf.set(qn("w:eastAsia"), SONG)
        rf.set(qn("w:ascii"), "Times New Roman")
        rf.set(qn("w:hAnsi"), "Times New Roman")
        pf = st.paragraph_format
        pf.left_indent = Cm(0.0 if lvl == 1 else 0.52 * (lvl - 1))
        pf.first_line_indent = Pt(0)
        pf.space_before = Pt(4 if lvl == 1 else 0.5)
        pf.space_after = Pt(0.5)
        pf.line_spacing = 1.0
        pf.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT,
                                  WD_TAB_LEADER.DOTS)


def setup_page(section):
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(3.17)
    section.header_distance = Cm(1.5)
    section.footer_distance = Cm(1.5)


def set_page_numbering(section, fmt="decimal", start=1):
    sectPr = section._sectPr
    for old in sectPr.findall(qn("w:pgNumType")):
        sectPr.remove(old)
    el = OxmlElement("w:pgNumType")
    el.set(qn("w:fmt"), fmt)
    el.set(qn("w:start"), str(start))
    sectPr.insert_element_before(
        el, "w:cols", "w:formProt", "w:vAlign", "w:noEndnote", "w:titlePg",
        "w:textDirection", "w:bidi", "w:rtlGutter", "w:docGrid",
        "w:printerSettings", "w:sectPrChange")


def build_header_footer(section, with_number=True, with_total=True):
    section.header.is_linked_to_previous = False
    hp = section.header.paragraphs[0]
    hp.text = ""
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hp.paragraph_format.space_after = Pt(0)
    r = hp.add_run(SHORT_TITLE)
    set_run_font(r, SONG, SONG, size=9, color=GRAY_TXT)
    pPr = hp._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "808080")
    bdr.append(bottom)
    pPr.append(bdr)

    section.footer.is_linked_to_previous = False
    fp = section.footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if not with_number:
        return
    fp.paragraph_format.space_before = Pt(0)
    r = fp.add_run("第 ")
    set_run_font(r, SONG, SONG, size=9)
    add_field(fp, " PAGE ", "1", size=9)
    if with_total:
        r = fp.add_run(" 页 共 ")
        set_run_font(r, SONG, SONG, size=9)
        add_field(fp, " NUMPAGES ", "1", size=9)
    r = fp.add_run(" 页")
    set_run_font(r, SONG, SONG, size=9)


def clear_header_footer(section):
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    section.header.paragraphs[0].text = ""
    section.footer.paragraphs[0].text = ""


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
class Builder:
    def __init__(self, doc):
        self.doc = doc
        self.stats = {"paras": 0, "tables": 0, "images": 0, "headings": 0}
        self.missing_images = []
        self.chapter_stats = []
        self.section_first_h1 = True

    # ---- 封面 ----
    def cover(self, title, subtitle, infos):
        d = self.doc
        for _ in range(2):
            d.add_paragraph()
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(60)
        p.paragraph_format.space_after = Pt(18)
        r = p.add_run(title)
        set_run_font(r, HEI, HEI, size=22, bold=True, color=BLACK)
        p.paragraph_format.line_spacing = 1.5

        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run(subtitle)
        set_run_font(r, HEI, HEI, size=16, bold=False, color=BLACK)
        p.paragraph_format.line_spacing = 1.5

        for _ in range(3):
            d.add_paragraph()

        for label, value in infos:
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.6
            r = p.add_run(f"{label}：{value}")
            set_run_font(r, SONG, SONG, size=14, bold=False, color=BLACK)
        # 封面末留白
        for _ in range(2):
            d.add_paragraph()

    # ---- 标题 ----
    def heading(self, level, text, page_break=False, page_title=False):
        p = self.doc.add_paragraph(style=f"Heading {level}")
        if page_title:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(18)
        if level == 1 and self.section_first_h1:
            p.paragraph_format.page_break_before = False
            self.section_first_h1 = False
        size = 16 if page_title else {1: 16, 2: 14, 3: 12}[level]
        add_inline(p, text, size=size,
                   ascii_font="Times New Roman", ea_font=HEI, bold_all=True, color=BLACK)
        self.stats["headings"] += 1
        return p

    # ---- 段落 ----
    def para(self, text):
        p = self.doc.add_paragraph()
        add_inline(p, text)
        set_first_line_chars(p)
        self.stats["paras"] += 1

    def caption(self, text, keep_next=True):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.2
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.keep_with_next = keep_next
        add_inline(p, text, size=10.5, bold_all=True, color=BLACK)
        self.stats["paras"] += 1

    def figure_caption(self, text):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(12)
        p.paragraph_format.first_line_indent = Pt(0)
        add_inline(p, text, size=10.5, bold_all=True, color=BLACK)
        self.stats["paras"] += 1

    # ---- 列表 ----
    def list_item(self, text, indent=0, marker="•", num=None):
        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(-18)
        p.paragraph_format.left_indent = Pt(24 + indent * 21 + 18)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.5
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r = p.add_run(f"{num}. " if num else marker + " ")
        set_run_font(r, SONG, SONG, size=BODY_PT)
        add_inline(p, text)
        self.stats["paras"] += 1

    # ---- 引用 ----
    def quote(self, text):
        p = self.doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.6)
        pf.right_indent = Cm(0.3)
        pf.space_before = Pt(6)
        pf.space_after = Pt(6)
        pf.line_spacing = 1.4
        add_left_bar(p, "A6A6A6", 18)
        para_shade(p, "F4F4F4")
        add_inline(p, text, size=10.5, color=GRAY_TXT)
        self.stats["paras"] += 1

    # ---- 代码块 ----
    def code(self, lines):
        for ln in lines:
            p = self.doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(0.4)
            pf.first_line_indent = Pt(0)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            pf.line_spacing = 1.0
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            para_shade(p, "F5F5F5")
            r = p.add_run(ln if ln.strip() else " ")
            set_run_font(r, MONO, SONG, size=CODE_PT)
            self.stats["paras"] += 1

    # ---- 图片 ----
    def image(self, alt, src):
        path = self.resolve(src)
        if path is None or not path.exists():
            self.missing_images.append(src)
            print(f"  [缺图] {src}  (alt={alt})")
            t = self.doc.add_table(rows=1, cols=1)
            t.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = t.cell(0, 0)
            cell.width = Cm(15)
            tr = t.rows[0]
            tr.height = Cm(5)
            tcPr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "EDEDED")
            tcPr.append(shd)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(f"【缺少图片】{src}\n{alt}")
            set_run_font(r, SONG, SONG, size=10.5, bold=True, color=RED)
            if alt:
                self.figure_caption(alt)
            return
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.keep_with_next = True
        run = p.add_run()
        run.add_picture(str(path), width=Cm(15))
        self.stats["images"] += 1
        if alt:
            self.figure_caption(alt)

    @staticmethod
    def resolve(src):
        src = src.replace("\\", "/")
        cands = [DOCS / src, ROOT / src, ROOT / "deliverables" / src,
                 ROOT / "deliverables" / "figures" / Path(src).name]
        for c in cands:
            if c.exists():
                return c
        return None

    # ---- 三线表 ----
    def table(self, header, rows, caption=None):
        if caption:
            self.caption(caption)
        ncol = len(header)
        rows = [r + [""] * (ncol - len(r)) if len(r) < ncol else r[:ncol] for r in rows]
        rows = [r for r in rows if any(c.strip() for c in r)]
        t = self.doc.add_table(rows=1 + len(rows), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        tblPr = t._tbl.tblPr
        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:w"), str(int(TEXT_W_CM / 2.54 * 1440)))
        tblW.set(qn("w:type"), "dxa")
        tblPr.insert_element_before(tblW, "w:jc", "w:tblCellSpacing", "w:tblInd",
                                    "w:tblBorders", "w:shd", "w:tblLayout",
                                    "w:tblCellMar", "w:tblLook")
        # 三线
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "bottom"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "12")
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), "000000")
            borders.append(e)
        for edge in ("left", "right", "insideH", "insideV"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "none")
            e.set(qn("w:sz"), "0")
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), "auto")
            borders.append(e)
        tblPr.insert_element_before(borders, "w:shd", "w:tblLayout",
                                    "w:tblCellMar", "w:tblLook", "w:tblCaption",
                                    "w:tblDescription")

        # 列宽：按“显示宽度”加权 + 不可断词最小宽度（宽表自动降字号、窄边距）。
        # 若所有列的不可断词宽度之和仍超出正文宽度，继续降字号直到放得下，
        # 否则 JWT_REFRESH_TTL_DAYS 这类标识符会被截成 “DA / YS”。
        def _split_code(txt):
            """把单元格文本拆成 [(片段, 是否行内代码)]；行内代码用 Consolas 且字号 -1.5，
            度量必须按等宽字体算，否则附录里的 `JWT_REFRESH_TTL_DAYS` 会被截断。"""
            parts = re.split(r"`([^`]+)`", txt or "")
            out = []
            for i, part in enumerate(parts):
                if part:
                    out.append((part, i % 2 == 1))
            return out

        def _code_em(part, fs_):
            return len(part) * 0.55 * ((fs_ - 1.5) / fs_) * 2.0

        def analyze(fs_):
            cjk_cm = fs_ * 0.03528
            code_cm = 0.55 * max(fs_ - 1.5, 4.0) * 0.03528
            mar_lr = 60 if ncol > 6 else 80
            pad = mar_lr / 1440.0 * 2.54 * 2

            def _w(txt):
                em = 0.0
                for part, is_code in _split_code(txt):
                    if is_code:
                        em += _code_em(part, fs_)
                    else:
                        for ch in re.sub(r"[*]", "", part):
                            em += 2.0 if ord(ch) > 0x2E80 else 1.05
                return em

            def _ach(ch):
                # ASCII 单字符宽度（em）→ cm；大写与下划线明显更宽，
                # 按 0.0175 一刀切会低估 JWT_REFRESH_TTL_DAYS 这类标识符，
                # 导致 Word 里被撕成 “..._DA / YS”。
                if ch.isupper():
                    k = 1.32            # 半角大写约 0.66em(=1.32 半角单位)；此前 0.8 严重低估
                elif ch.isdigit():
                    k = 0.98
                elif ch in "_+=:|-":
                    k = 0.98
                elif ch in ".,;'":
                    k = 0.30
                else:
                    k = 0.95
                return k * cjk_cm / 2.0

            def _min_cm(txt):
                best = 0.0
                run = 0.0
                for part, is_code in _split_code(txt):
                    if is_code:
                        run += len(part) * code_cm
                        best = max(best, run)
                        continue
                    for ch in re.sub(r"[*]", "", part):
                        if ch in " 、，。；：（）()【】[]+·":
                            run = 0.0
                            continue
                        run += cjk_cm if ord(ch) > 0x2E80 else _ach(ch)
                        best = max(best, run)
                # 含 “/” 或超长（>26 字符）的词按路径处理：允许在 “/” 处断行
                plain = re.sub(r"`[^`]+`", "", txt or "")
                for word in re.split(r"[\s、，。；：（）()【】\[\]]+", plain):
                    if not word or ("/" not in word and len(word) <= 26):
                        continue
                    run = 0.0
                    for ch in word + "/":
                        if ch == "/":
                            best = max(best, run)
                            run = 0.0
                            continue
                        run += cjk_cm if ord(ch) > 0x2E80 else _ach(ch)
                    best = max(best, run)
                return best + pad

            ws_, ms_ = [], []
            for c in range(ncol):
                cells = [header[c]] + [r[c] for r in rows]
                em = max([_w(x) for x in cells] + [3.0])
                ws_.append(max(4.0, min(em, 30.0)))
                ms_.append(min(max(max(_min_cm(x) for x in cells), 1.45), 8.0))
            return ws_, ms_, mar_lr

        # 列宽策略（与 Word 实际排版对齐）：
        #   1) 宽表（列数 >= 5）统一小五 9pt —— 表宽永远够，避免靠压列宽硬塞；
        #   2) 短标签列（必填/密级/序号/等级…）固定 1.1–1.3cm 并让表头不换行；
        #   3) 其余列按“表头宽度 / 最长不可断词”取下限，正文列最小 2.2cm；
        #   4) 余量按各列内容宽度比例分配，单列上限 8cm；超宽则先压正文列、再压标签列。
        def _disp_em(txt, fs_):
            em = 0.0
            for part, is_code in _split_code(txt or ""):
                if is_code:
                    em += len(part) * 0.55 * ((fs_ - 1.5) / fs_) * 2.0
                else:
                    for ch in re.sub(r"[*]", "", part):
                        em += 2.0 if ord(ch) > 0x2E80 else 1.05
            return em

        is_label = [(header[c] or "").strip() in SHORT_LABELS for c in range(ncol)]

        def plan(fs_):
            """按给定字号算“不可再窄”的列宽：短标签列 1.1–1.3cm、正文列 ≥2.2cm、
            表头必须放得下（noWrap）。返回 (列宽列表, 内容权重, 边距)。"""
            ws_, ms_, mar_lr = analyze(fs_)
            cjk_cm_ = fs_ * 0.03528
            pad_cm_ = mar_lr / 1440.0 * 2.54 * 2
            hdr = [_disp_em(header[c], fs_) * cjk_cm_ / 2.0 + pad_cm_
                   for c in range(ncol)]
            fl = []
            for c in range(ncol):
                if is_label[c]:
                    fl.append(min(max(hdr[c], 1.1), 2.0))
                elif c == 0:
                    # 首列多为标识符/层名：至少 3.0cm，避免 “DATABASE_READ_URL” 被腰斩
                    fl.append(max(3.0, min(max(hdr[c], min(ms_[c], 8.0)), 8.0)))
                else:
                    fl.append(max(1.8, min(max(hdr[c], min(ms_[c], 8.0)), 8.0)))
            return fl, ws_, mar_lr

        # 字号阶梯：窄表五号 10.5pt；列多则从小五 9pt 起，实在放不下再逐级降，
        # 只为避免把 `GLM_BREAKER_FAILURE_THRESHOLD` 这类标识符从中间撕开。
        cands = [10.5] if ncol < 5 else [9.0, 8.5, 8.0, 7.5]
        chosen = None
        best_over = None                      # (超额比例, fs, fl, ws, mar)
        for fs_c in cands:
            fl, ws_, mar_lr = plan(fs_c)
            over_ratio = (sum(fl) - TEXT_W_CM) / TEXT_W_CM
            if over_ratio <= 0.03:            # 允许 3% 内的轻微压缩，避免为 0.04cm 降字号
                chosen = (fs_c, fl, ws_, mar_lr)
                break
            if best_over is None or over_ratio < best_over[0]:
                best_over = (over_ratio, fs_c, fl, ws_, mar_lr)
        if chosen is None:
            if best_over is not None:
                _, fs_c, fl, ws_, mar_lr = best_over
            else:
                fs_c = cands[-1]
                fl, ws_, mar_lr = plan(fs_c)
            chosen = (fs_c, fl, ws_, mar_lr)
        fs, widths, ws_, mar_lr = chosen

        total = sum(widths)
        texts = [c for c in range(ncol) if not is_label[c]]
        if total < TEXT_W_CM:                       # 有富余：按内容宽度分配
            extra = TEXT_W_CM - total
            room = [max(0.0, 8.0 - widths[c]) if c in texts else 0.0
                    for c in range(ncol)]
            sroom = sum(room) or 1.0
            for c in range(ncol):
                widths[c] += extra * room[c] / sroom
        elif total > TEXT_W_CM:                     # 超宽：先压正文列，再压标签列
            over = total - TEXT_W_CM
            avail = sum(max(0.0, widths[c] - 1.05) for c in range(ncol))
            for c in range(ncol):
                d = max(0.0, widths[c] - 1.05)
                widths[c] -= over * d / (avail or 1.0)
        k = TEXT_W_CM / sum(widths)
        if abs(k - 1.0) > 0.002:                    # 归一化到版心宽度
            widths = [w * k for w in widths]
        wide = ncol >= 5
        if os.environ.get("TBL_DEBUG"):
            print("[TBL]", (caption or "")[:24], "fs=%.1f" % fs,
                  [round(w, 2) for w in widths])
        vpad = 28 if wide else 40                   # 上下边距（twips）
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)
        for row in t.rows:                          # 宽表行高下限 0.6cm
            trPr_ = row._tr.get_or_add_trPr()
            th_ = OxmlElement("w:trHeight")
            th_.set(qn("w:val"), "340" if wide else "300")
            th_.set(qn("w:hRule"), "atLeast")
            trPr_.append(th_)

        def fill_cell(cell, text, is_header=False):
            tcPr = cell._tc.get_or_add_tcPr()
            va = OxmlElement("w:vAlign")
            va.set(qn("w:val"), "center")
            tcPr.append(va)
            mar = OxmlElement("w:tcMar")
            for side, v in (("top", vpad), ("bottom", vpad), ("left", mar_lr), ("right", mar_lr)):
                m = OxmlElement(f"w:{side}")
                m.set(qn("w:w"), str(v))
                m.set(qn("w:type"), "dxa")
                mar.append(m)
            tcPr.append(mar)
            p = cell.paragraphs[0]
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.15
            long_cell = len(re.sub(r"[*`]", "", text)) > 12
            p.alignment = (WD_ALIGN_PARAGRAPH.CENTER if (is_header or not long_cell)
                           else WD_ALIGN_PARAGRAPH.LEFT)
            add_inline(p, text, size=fs, bold_all=is_header, color=BLACK)

        hdr = t.rows[0]
        trPr = hdr._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        trPr.append(th)
        for i, txt in enumerate(header):
            fill_cell(hdr.cells[i], txt, True)
            hdr.cells[i].paragraphs[0].paragraph_format.keep_with_next = True
            tcPr = hdr.cells[i]._tc.get_or_add_tcPr()
            bdr = OxmlElement("w:tcBorders")
            bot = OxmlElement("w:bottom")
            bot.set(qn("w:val"), "single")
            bot.set(qn("w:sz"), "8")
            bot.set(qn("w:space"), "0")
            bot.set(qn("w:color"), "000000")
            bdr.append(bot)
            tcPr.append(bdr)
            if is_label[i]:                     # 短标签表头不换行，避免“必/填”竖排
                nw = OxmlElement("w:noWrap")
                tcPr.append(nw)
            hdr.cells[i].width = Cm(widths[i])

        for ri, row in enumerate(rows, start=1):
            tr = t.rows[ri]
            trPr = tr._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit")
            trPr.append(cs)
            for ci, txt in enumerate(row):
                fill_cell(tr.cells[ci], txt)
                tr.cells[ci].width = Cm(widths[ci])

        self.stats["tables"] += 1
        # 表后间距
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run("")
        set_run_font(r, SONG, SONG, size=4)

    # ---- 目录 ----
    def toc_page(self):
        # “目 录”用普通段落 + 直接格式模拟一级标题：
        # 既不进目录（避免目录列出自己），也不占用 Heading 1 编号。
        tp = self.doc.add_paragraph()
        tpf = tp.paragraph_format
        tpf.page_break_before = True
        tpf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tpf.space_before = Pt(0)
        tpf.space_after = Pt(18)
        add_inline(tp, "目 录", size=16, ascii_font="Times New Roman",
                   ea_font=HEI, bold_all=True, color=BLACK)
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run()
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), "begin")
        r._r.append(fc)

        r = p.add_run()
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = ' TOC \\o "1-3" \\h \\z \\u '
        r._r.append(it)

        r = p.add_run()
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), "separate")
        r._r.append(fc)

        r = p.add_run("【请在此处右键选择“更新域”或按 F9 生成目录】")
        set_run_font(r, SONG, SONG, size=10.5, color=GRAY_TXT)

        r = p.add_run()
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), "end")
        r._r.append(fc)


# --------------------------------------------------------------------------
# 文件分组
# --------------------------------------------------------------------------
def discover(docs_dir):
    files = [p for p in sorted(docs_dir.glob("*.md")) if p.name not in SKIP_FILES]
    cover, chapters, appendix = [], [], []
    for p in files:
        stem = p.stem
        if stem.startswith("00"):
            cover.append(p)
        elif re.match(r"^\d{2}", stem):
            chapters.append((int(stem[:2]), p))
        elif stem.startswith("附录") or re.match(r"^[A-Z]_", stem):
            appendix.append((stem, p))
    chapters.sort(key=lambda x: x[0])
    appendix.sort(key=lambda x: x[0])
    return cover, [p for _, p in chapters], [p for _, p in appendix]


# 封面字段覆盖：任务书 2026.12.10 交任务书、2027.05 交成果，故封面日期写 2027 年 5 月。
# md 正文（00 文件）不修改，只在构建时覆盖展示值。
COVER_INFO_OVERRIDE = {"日 期": "2027 年 5 月", "日期": "2027 年 5 月"}


def parse_cover(blocks):
    """00 文件：首行 # 主标题、随后 ## 副标题、随后字段列表 -> (title, subtitle, infos, rest)。"""
    title, subtitle, infos, rest = None, None, [], []
    idx = 0
    if blocks and blocks[0]["t"] == "h" and blocks[0]["level"] == 1:
        title = blocks[0]["text"]
        idx = 1
    if idx < len(blocks) and blocks[idx]["t"] == "h" and blocks[idx]["level"] == 2:
        subtitle = blocks[idx]["text"]
        idx += 1
    while idx < len(blocks):
        b = blocks[idx]
        if b["t"] == "ul" and "**" in b["text"]:
            m = re.match(r"^\*\*(.+?)\*\*[：:]\s*(.*)$", b["text"])
            if m:
                infos.append((m.group(1).strip(), m.group(2).strip()))
                idx += 1
                continue
        break
    # 封面上需要与任务书时间线一致的字段（md 里的值保持原样不动）
    infos = [(k, COVER_INFO_OVERRIDE.get(k, v)) for k, v in infos]
    rest = blocks[idx:]
    return title, subtitle, infos, rest


def count_words(blocks):
    cjk = latin = 0
    for b in blocks:
        text = ""
        if b["t"] in ("p", "quote", "ul", "ol", "task"):
            text = b.get("text", "")
        elif b["t"] == "h":
            text = b["text"]
        elif b["t"] == "table":
            text = " ".join(b["header"]) + " " + " ".join(" ".join(r) for r in b["rows"])
        elif b["t"] == "code":
            text = "\n".join(b["lines"])
        text = re.sub(r"\*\*|`", "", text)
        cjk += len(re.findall(r"[\u4e00-\u9fff]", text))
        latin += len(re.findall(r"[A-Za-z0-9][A-Za-z0-9._/%-]*", text))
    return cjk + latin


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build(docs_dir=DOCS, out=OUT):
    print(f"源目录: {docs_dir}")
    cover_files, chapters, appendix = discover(docs_dir)
    print(f"封面: {[p.name for p in cover_files]}")
    print(f"章节: {[p.name for p in chapters]}")
    print(f"附录: {[p.name for p in appendix]}")
    have_nums = {int(p.stem[:2]) for p in chapters}
    missing = [f"{i:02d}" for i in range(1, 11) if i not in have_nums]
    if missing:
        print(f"  [告警] 缺章: {', '.join(missing)}")

    doc = Document()
    setup_styles(doc)
    sec1 = doc.sections[0]
    setup_page(sec1)
    clear_header_footer(sec1)
    b = Builder(doc)

    # ---- 封面 ----
    ctitle, csub, cinfos, crest = parse_cover(
        attach_captions(parse_markdown(cover_files[0].read_text(encoding="utf-8")))
    ) if cover_files else (TITLE, "", [], [])
    b.cover(ctitle or TITLE, csub or "", cinfos or [("单 位", "XX 职业技术学院"), ("姓 名", "XXX")])

    # ---- 前置部分（罗马页码） ----
    sec2 = doc.add_section(WD_SECTION.NEW_PAGE)
    setup_page(sec2)
    set_page_numbering(sec2, "lowerRoman", 1)
    build_header_footer(sec2, True, with_total=False)
    b.section_first_h1 = True  # 前置部分首个标题不额外分页

    if crest:
        cblocks = attach_captions(crest)
        for blk in cblocks:
            if blk["t"] == "h" and re.sub(r"\s+", "", blk["text"]).lower() in (
                    "摘要", "abstract"):
                # 摘要 / Abstract 一律进一级标题（进目录一级条目），
                # 但是页面标题式排版（居中、三号、段后间距）。
                b.heading(1, blk["text"], page_title=True)
            else:
                render_block(b, blk)

    # 目录（Heading 1 自带段前分页）
    b.section_first_h1 = False
    b.toc_page()

    # ---- 正文（阿拉伯页码，从 1 开始） ----
    sec3 = doc.add_section(WD_SECTION.NEW_PAGE)
    setup_page(sec3)
    set_page_numbering(sec3, "decimal", 1)
    build_header_footer(sec3, True, with_total=True)
    b.section_first_h1 = True

    all_chapters = [(p, "chapter") for p in chapters] + [(p, "appendix") for p in appendix]
    for p, kind in all_chapters:
        text = p.read_text(encoding="utf-8")
        blocks = attach_captions(parse_markdown(text))
        n_img_before = b.stats["images"]
        n_tbl_before = b.stats["tables"]
        n_para_before = b.stats["paras"]
        for blk in blocks:
            render_block(b, blk)
        cjk = count_words(blocks)
        b.chapter_stats.append({
            "file": p.name,
            "words": cjk,
            "tables": b.stats["tables"] - n_tbl_before,
            "images": b.stats["images"] - n_img_before,
            "paras": b.stats["paras"] - n_para_before,
        })

    # 打开时更新域
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is None:
        uf = OxmlElement("w:updateFields")
        uf.set(qn("w:val"), "true")
        settings.insert_element_before(
            uf, "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat",
            "w:docVars", "w:rsids", "m:mathPr", "w:themeFontLang",
            "w:clrSchemeMapping", "w:shapeDefaults", "w:decimalSymbol",
            "w:listSeparator")
    doc.core_properties.title = TITLE
    doc.core_properties.author = "XXX"
    doc.core_properties.subject = "毕业设计 · 生产化改造与重构方案"

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print(f"\n[已生成] {out}  {out.stat().st_size / 1024:.0f} KB")
    report(b, out, chapters, appendix, missing)
    return out



def fix_quotes(text):
    """把段落里的 ASCII 双引号成对转成中文弯引号；跳过行内代码片段。"""
    parts = text.split("`")
    out = []
    for i, seg in enumerate(parts):
        if i % 2 == 1 or seg.count('"') == 0 or seg.count('"') % 2:
            out.append(seg)
            continue
        buf = []
        opening = True
        for ch in seg:
            if ch == '"':
                buf.append("\u201c" if opening else "\u201d")
                opening = not opening
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "`".join(out)


def render_block(b, blk):
    t = blk["t"]
    if "text" in blk:
        blk["text"] = fix_quotes(blk["text"])
    if t == "h":
        txt = blk["text"]
        if blk["level"] == 1:
            txt = re.sub(r"^第\s*(\d+)\s*章", r"第 \1 章", txt)
            txt = re.sub(r"^(附录)\s*([A-Ca-c])(?=\s|\u3000|$)", r"\1 \2", txt)
        b.heading(blk["level"], txt)
    elif t == "p":
        b.para(blk["text"])
    elif t == "quote":
        b.quote(blk["text"])
    elif t == "code":
        b.code(blk["lines"])
    elif t == "image":
        b.image(blk["alt"], blk["src"])
    elif t == "table":
        b.table(blk["header"], blk["rows"], blk.get("caption"))
    elif t == "ul":
        b.list_item(blk["text"], blk["indent"] // 2, "•")
    elif t == "ol":
        b.list_item(blk["text"], blk["indent"] // 2, num=blk["num"])
    elif t == "task":
        b.list_item(blk["text"], blk["indent"] // 2, "☐" if not blk["checked"] else "☑")
    elif t == "hr":
        pass


def report(b, out, chapters, appendix, missing):
    print("\n=== 构建统计 ===")
    print(f"{'文件':40s}{'字数':>8s}{'表格':>6s}{'图片':>6s}")
    total_w = 0
    for cs in b.chapter_stats:
        total_w += cs["words"]
        print(f"{cs['file'][:38]:40s}{cs['words']:8d}{cs['tables']:6d}{cs['images']:6d}")
    print(f"{'合计':40s}{total_w:8d}{b.stats['tables']:6d}{b.stats['images']:6d}")
    print(f"段落 {b.stats['paras']} · 表格 {b.stats['tables']} · 图片 {b.stats['images']} · 标题 {b.stats['headings']}")
    if b.missing_images:
        print(f"缺图清单({len(b.missing_images)}): {b.missing_images}")
    if missing:
        print(f"缺章清单: {missing}")
    est = int(total_w / 620 + b.stats["tables"] * 0.35 + b.stats["images"] * 0.55 + 4)
    print(f"页数估算: 约 {est} 页（正文）")

    # ---- 自检 ----
    print("\n=== 自检 ===")
    d2 = Document(str(out))
    n_par = len(d2.paragraphs)
    n_tbl = len(d2.tables)
    n_img = len(d2.inline_shapes)
    heads = sum(1 for p in d2.paragraphs if p.style.name.startswith("Heading"))
    print(f"重新打开: 段落 {n_par} · 表格 {n_tbl} · 内联图片 {n_img} · 标题 {heads}")
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml")
        from lxml import etree
        etree.fromstring(xml)
        print("document.xml 解析: OK")
        names = z.namelist()
        body = "".join(z.read(n).decode("utf-8", "ignore") for n in names
                       if n.startswith("word/") and n.endswith(".xml"))
        hits = [i for i in range(len(body)) if body.startswith("待补充", i)]
        print(f"『待补充』出现次数: {len(hits)}（文档正文中引用该字样属正常，仅需要求 0 处时告警）")
        for i in hits[:3]:
            frag = body[max(0, i - 60):i + 40].replace("\n", " ")
            frag = re.sub(r"<[^>]+>", "", frag)
            print(f"   … {frag.strip()}")
        print(f"包内文件数: {len(names)} · 媒体: {len([x for x in names if x.startswith('word/media/')])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(DOCS))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    build(Path(args.docs), Path(args.out))


if __name__ == "__main__":
    main()

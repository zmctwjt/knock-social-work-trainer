# -*- coding: utf-8 -*-
"""绘图基础库：纯几何 SVG + Chrome 无头渲染 + Pillow 裁白边。

设计原则
- 所有图由 Python 以绝对坐标生成 SVG，坐标可控，避免 HTML 流式布局的错位；
- 文本宽度按字符类别估算（CJK=1.0em，ASCII≈0.55em），超宽即报错，强制作者改布局；
- 渲染后统一裁剪白边并缩放到 1600px 宽，保证 docx 中 15cm 宽度下清晰。
"""
import os
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image, ImageChops

# ---------------------------------------------------------------- 调色板
NAVY = "#1F3A5F"
NAVY2 = "#2E5580"
NAVY3 = "#4C6E96"
BLUE_FILL = "#E9F0F8"
BLUE_BORDER = "#A8BDD4"
BLUE_SOFT = "#F4F8FC"
ORANGE = "#D97706"
ORANGE_FILL = "#FDF3E4"
ORANGE_BORDER = "#E9B678"
ORANGE_SOFT = "#FEF9F1"
GRAY = "#6B7280"
GRAY_FILL = "#F3F4F6"
GRAY_BORDER = "#D1D5DB"
TEXT = "#1F2937"
TEXT2 = "#374151"
WHITE = "#FFFFFF"

FONT = "'Microsoft YaHei','Microsoft YaHei UI','PingFang SC','Segoe UI',sans-serif"

CHROME_CANDIDATES = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
]


# ---------------------------------------------------------------- 文本度量
def _char_w(ch, size):
    if ch == " ":
        return size * 0.28
    if ch in "\t":
        return size * 0.56
    o = ord(ch)
    if o > 0x2E7F:  # CJK / 全角标点
        return size * 1.0
    if ch in "，。、；：！“”‘’（）《》【】—…·":
        return size * 1.0
    if ch.isdigit():
        return size * 0.56
    if ch.isupper():
        return size * 0.64
    if ch in "iljtfr.,:;'|!()[]{}":
        return size * 0.42
    if ch in "mwMW@%":
        return size * 0.85
    return size * 0.55


def tw(s, size):
    return sum(_char_w(c, size) for c in s)


def _tokens(s):
    """把字符串切分为不可断开的 token：ASCII 连续词 / 单个 CJK 字符 / 单个空格。"""
    out, buf = [], ""
    for ch in s:
        if ch == " ":
            if buf:
                out.append(buf)
                buf = ""
            out.append(" ")
        elif ord(ch) > 0x2E7F or unicodedata.east_asian_width(ch) in ("W", "F"):
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


def wrap_text(s, maxw, size):
    """按估算宽度折行，返回行列表。单 token 超宽时按字符硬切。"""
    if not s:
        return [""]
    lines, cur = [], ""
    for tok in _tokens(s):
        cand = cur + tok
        if tw(cand, size) <= maxw or not cur:
            if tok == " " and not cur:
                continue
            cur = cand
        else:
            lines.append(cur.rstrip())
            cur = "" if tok == " " else tok
    if cur:
        lines.append(cur.rstrip())
    # 处理超宽单行（长英文单词 / 长数字）
    out = []
    for ln in lines:
        while tw(ln, size) > maxw and len(ln) > 1:
            cut = len(ln)
            while cut > 1 and tw(ln[:cut], size) > maxw:
                cut -= 1
            out.append(ln[:cut])
            ln = ln[cut:]
        out.append(ln)
    return out


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------- 画布
class Fig:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []
        self._markers = {}
        self.warnings = []

    # -- 基础图元 --------------------------------------------------
    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill=WHITE, stroke=NAVY, sw=1.6, rx=6, dash=None, opacity=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>'
        )

    def line(self, pts, color=NAVY, sw=2, dash=None, opacity=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity is not None else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}"{d}{o}/>')

    def _marker(self, color):
        key = color.replace("#", "")
        mid = f"arw_{key}"
        if mid not in self._markers:
            self._markers[mid] = (
                f'<marker id="{mid}" viewBox="0 0 12 12" refX="11" refY="6" '
                f'markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" '
                f'orient="auto-start-reverse"><path d="M0,0 L12,6 L0,12 z" fill="{color}"/></marker>'
            )
        return mid

    def arrow(self, pts, color=NAVY, sw=2, dash=None, both=False, label=None,
              label_at=None, label_size=13, label_color=None, label_bg=True):
        if len(pts) < 2:
            return
        mid = self._marker(color)
        mk = f' marker-end="url(#{mid})"' + (f' marker-start="url(#{mid})"' if both else "")
        d = f' stroke-dasharray="{dash}"' if dash else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(
            f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linejoin="round"{d}{mk}/>'
        )
        if label:
            if label_at is None:
                i = len(pts) // 2 - 1
                x = (pts[i][0] + pts[i + 1][0]) / 2
                y = (pts[i][1] + pts[i + 1][1]) / 2
            else:
                x, y = label_at
            self.label(x, y, label, size=label_size, color=label_color or color, bg=label_bg)

    def label(self, x, y, s, size=13, color=TEXT2, bg=True, weight="400", anchor="middle"):
        lw = tw(s, size) + 8
        if bg:
            self.add(
                f'<rect x="{x - lw / 2:.1f}" y="{y - size * 0.78:.1f}" width="{lw:.1f}" '
                f'height="{size * 1.32:.1f}" rx="3" fill="#FFFFFF" opacity="0.92"/>'
            )
        self.txt(x, y + size * 0.28, s, size=size, color=color, weight=weight, anchor=anchor)

    def txt(self, x, y, s, size=14, color=TEXT, weight="400", anchor="middle", opacity=None):
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{o}>{esc(s)}</text>'
        )

    def raw(self, s):
        self.add(s)

    # -- 组合图元 --------------------------------------------------
    def block(self, x, y, w, h, title=None, lines=(), fill=BLUE_FILL, stroke=BLUE_BORDER,
              sw=1.6, dash=None, title_size=16, body_size=13, title_color=NAVY,
              body_color=TEXT2, pad=14, accent=None, align="center", line_gap=1.5,
              tag=None, tag_color=ORANGE):
        """圆角块：标题 + 若干行说明，整体垂直居中。超宽自动折行并记录告警。"""
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=sw, dash=dash)
        if accent:
            self.rect(x, y, 5, h, fill=accent, stroke=accent, sw=0, rx=2)
        inner = w - 2 * pad
        if tag:
            tgw = tw(tag, 12) + 16
            self.rect(x + w - tgw - 8, y + 8, tgw, 20, fill=tag_color, stroke=tag_color, sw=0, rx=4)
            self.txt(x + w - tgw / 2 - 8, y + 22, tag, size=12, color=WHITE, weight="700")

        wrapped = []
        for ln in lines:
            for p in wrap_text(ln, inner, body_size):
                if tw(p, body_size) > inner + 1:
                    self.warnings.append(f"溢出: {p!r} > {inner:.0f}")
                wrapped.append(p)

        title_h = title_size * 1.4 if title else 0
        gap = 9 if (title and wrapped) else 0
        body_h = len(wrapped) * body_size * line_gap
        total = title_h + gap + body_h
        cur = y + (h - total) / 2.0
        if title:
            self.txt(x + w / 2, cur + title_size * 1.02, title, size=title_size,
                     color=title_color, weight="700", anchor="middle")
            cur += title_h + gap
        for p in wrapped:
            self.txt(x + w / 2, cur + body_size * 0.95, p, size=body_size,
                     color=body_color, anchor="middle")
            cur += body_size * line_gap

    def banner(self, x, y, w, h, text, fill=BLUE_FILL, stroke=BLUE_BORDER, color=NAVY,
               size=14, weight="400", dash=None, accent=None):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=1.6, dash=dash)
        if accent:
            self.rect(x, y, 5, h, fill=accent, stroke=accent, sw=0, rx=2)
        lines = wrap_text(text, w - 36, size)
        lh = size * 1.45
        cur = y + (h - len(lines) * lh) / 2.0
        for ln in lines:
            self.txt(x + w / 2, cur + size * 0.98, ln, size=size, color=color, weight=weight)
            cur += lh

    def chip(self, x, y, label, size=13, fill=WHITE, stroke=BLUE_BORDER, color=NAVY,
             w=None, h=28, rx=5, weight="400"):
        cw = w or (tw(label, size) + 24)
        self.rect(x, y, cw, h, fill=fill, stroke=stroke, sw=1.4, rx=rx)
        self.txt(x + cw / 2, y + h / 2 + size * 0.36, label, size=size, color=color, weight=weight)
        return cw

    def diamond(self, cx, cy, r, fill=ORANGE, stroke=ORANGE, sw=1.5):
        pts = f"{cx},{cy - r} {cx + r},{cy} {cx},{cy + r} {cx - r},{cy}"
        self.add(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def circle(self, cx, cy, r, fill=WHITE, stroke=NAVY, sw=1.6):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    # -- 输出 ------------------------------------------------------
    def svg(self):
        defs = "".join(self._markers.values())
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">'
            f'<defs>{defs}</defs>'
            f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="#FFFFFF"/>'
            + "".join(self.parts)
            + "</svg>"
        )


# ---------------------------------------------------------------- 渲染
def find_chrome():
    for p in CHROME_CANDIDATES:
        if p and Path(p).exists():
            return p
    raise RuntimeError("未找到 Chrome，请检查安装路径")


def render(fig, out_png, target_w=1600, verbose=True):
    chrome = find_chrome()
    tmpdir = Path(tempfile.gettempdir()) / "docgen_figs"
    tmpdir.mkdir(parents=True, exist_ok=True)
    html_path = tmpdir / (Path(out_png).stem + ".html")
    shot = tmpdir / (Path(out_png).stem + ".png")

    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<style>html,body{margin:0;padding:0;background:#fff;overflow:hidden;}svg{display:block;}</style>"
        f"</head><body>{fig.svg()}</body></html>"
    )
    html_path.write_text(html, encoding="utf-8")
    url = "file:///" + str(html_path).replace("\\", "/").replace(" ", "%20")
    profile = tmpdir / "profile"
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={profile}",
        "--force-device-scale-factor=2",
        f"--window-size={fig.w},{fig.h}",
        "--virtual-time-budget=2500",
        f"--screenshot={shot}",
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not shot.exists():
        raise RuntimeError(f"Chrome 截图失败: {r.stderr[-800:]}")

    img = Image.open(shot).convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if bbox:
        img = img.crop(bbox)
    # 四周留 22px 白边（trim 后补回，避免贴边/压字）
    pad = 22
    canvas = Image.new("RGB", (img.width + pad * 2, img.height + pad * 2), (255, 255, 255))
    canvas.paste(img, (pad, pad))
    img = canvas
    if img.width != target_w:
        nh = round(img.height * target_w / img.width)
        img = img.resize((target_w, nh), Image.LANCZOS)
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    if verbose:
        size = out.stat().st_size / 1024
        print(f"  [ok] {out.name}  {img.width}x{img.height}  {size:.0f} KB")
    for w in fig.warnings:
        print(f"  [WARN] {out_png}: {w}")
    return img.size

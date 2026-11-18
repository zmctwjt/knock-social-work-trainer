# docgen —— 文档构建工具链说明

本目录是毕业设计交付物《叩门 AI 陪练舱 · 生产化改造与重构方案》的**排版与出图流水线**。
所有 Word / Excel / 配图均由脚本生成，**不要手工修改产出文件**——改了会在下一次构建时被覆盖。

---

## 1. 目录与文件

| 文件 | 作用 |
| --- | --- |
| `figlib.py` | 配图绘制的底层库：`Fig` 类（rect / line / arrow / label / txt / block / banner / chip / diamond / circle / svg）、文本宽度估算与折行、Chrome 无头渲染 + Pillow 裁白边 + 统一 1600 宽 |
| `render_figures.py` | 7 张配图的版面定义；支持按序号渲染，如 `render_figures.py 3 5` |
| `build_docx.py` | Markdown → DOCX 构建器（封面、摘要、TOC 域、三级标题、三线表、代码块、图片、检查单、页眉页脚、分节页码） |
| `make_xlsx.py` | 生成 `deliverables/重构实施计划.xlsx`（WBS / 甘特 / 风险登记册 三个 sheet） |
| `../figures/fig-0x-*.png` | 构建器与文档正文共同引用的配图 |

产出的交付物：

- `deliverables/叩门AI陪练舱_生产化改造与重构方案.docx`
- `deliverables/重构实施计划.xlsx`
- `deliverables/figures/fig-01…07` 共 7 张 1600px 宽 PNG

---

## 2. 依赖

- **Python 3.12**：`work/pyenv/Scripts/python.exe`（仓库内虚拟环境）
- 第三方库：`python-docx`、`openpyxl`、`Pillow`、`lxml`
- **Google Chrome**（配图渲染）：`C:/Program Files/Google/Chrome/Application/chrome.exe`
- **Microsoft Word**（可选，仅用于导出 PDF 做目视验收）：Office16 的 `WINWORD.EXE`

安装（必须用 `uv`，本机 `pip` 代理不可用）：

```bash
C:/Users/ZMC/.local/bin/uv.exe pip install --python work/pyenv/Scripts/python.exe \
    python-docx openpyxl pillow lxml
```

---

## 3. 构建

在仓库根目录 `F:\毕业设计` 执行（Windows 中文环境需带 `PYTHONIOENCODING=utf-8`）：

```bash
# 1) 渲染全部配图
PYTHONIOENCODING=utf-8 work/pyenv/Scripts/python.exe deliverables/docgen/render_figures.py

# 2) 构建 Word（自动按 00 → 01…10 → 附录 A/B/C 的顺序取章节）
PYTHONIOENCODING=utf-8 work/pyenv/Scripts/python.exe deliverables/docgen/build_docx.py

# 3) 生成实施计划 Excel
PYTHONIOENCODING=utf-8 work/pyenv/Scripts/python.exe deliverables/docgen/make_xlsx.py
```

三个脚本都是**幂等可重跑**的：直接覆盖产物，不需要清理。

### 章节发现规则

`build_docx.py` 通过自定义的 `CHAPTER_ORDER` 列表按固定序号查找 `deliverables/docs/` 下的文件：

- `00_封面与摘要.md` → 封面 + 摘要页 + Abstract + 目录
- `01…10_*.md` → 第 1…10 章
- `附录A_*.md` / `附录B_*.md` / `附录C_*.md` → 附录

**缺章不会中断构建**，只在控制台打印 `[缺章]` 并跳过；构建末尾会汇总缺章清单。新增章节时文件名前缀（`05_`、`附录A_`）必须保持不变。

### 构建输出（控制台）应关注的字段

```
[章节] 01 现状分析  9155 字  9 表  1 图
...
[汇总] 正文 xx,xxx 字 · 表格 xx · 图片 x · 标题 xxx
[缺章] 05 后端…, 06 数据库…
[自检] document.xml 解析 OK · 重开 OK · 段落 1217 / 表格 101 / 图片 5 / 标题 266 · [待补充] 命中 1 处
```

`[待补充]` 命中若来自正文引用（如“不得残留 `[待补充]` 字样”的验收条目）属正常，构建器会打印命中上下文供核对。

---

## 4. 配图流水线

1. `render_figures.py` 用 Python 拼出**绝对定位的 HTML**（内联 CSS，不依赖任何前端库/网络）；
2. 调 Chrome 无头模式 `--force-device-scale-factor=2` 截图（2 倍像素密度，保证文字锐利）；
3. Pillow 自动裁掉四周白边、留 12px 内边距，再等比缩放到 **1600px 宽**；
4. 输出到 `deliverables/figures/`。

配色与规范（与 `docs/STYLE.md` 第 7 节一致）：白底、主色深蓝 `#1F3A5F`、强调橙 `#D97706`、圆角 6px、无阴影、正文字号 ≥ 13px、箭头单向清晰、信息不重叠不溢出。

| 文件名 | 内容 | 用在 |
| --- | --- | --- |
| `fig-01-current-arch.png` | 现状运行时架构（Node 单进程 8787 + GLM + Supabase） | 图 1-1 |
| `fig-02-target-arch.png` | 目标分层架构（接入/应用/领域数据/外部/横切） | 图 3-1 |
| `fig-03-deploy-topology.png` | 生产部署拓扑（Ingress → 3×Pod → PG 主从/Redis/智谱 + 旁挂观测） | 图 4-1 |
| `fig-04-er.png` | 数据模型 ER（10 表主外键） | 图 6-1 |
| `fig-05-gantt.png` | 13 周 5 阶段甘特（20 任务 + M1–M5） | 图 9-1 |
| `fig-06-request-chain.png` | 一次 AI 评分请求的完整链路与降级分支 | 图 5-1 |
| `fig-07-migration.png` | 绞杀者迁移四态（v1→v4 流量比例与判定指标） | 图 9-2 |

**每张图都必须用 `read_image` 目视验收**：检查文字是否溢出/重叠、箭头是否指错、标签是否被裁。改完版面重跑 `render_figures.py <序号>` 即可。

---

## 5. Word 排版实现要点

- **三节结构**：封面（无页眉页脚）→ 前置（摘要 / Abstract / 目录，页码 `i, ii, iii…`）→ 正文（`1, 2, 3…` 重新起算）。靠 `w:pgNumType` 的 `fmt` + `start` 实现，页眉页脚按 `sectPr` 分别挂载。
- **自动目录**：插入 `TOC \o "1-3" \h \z \u` 域，并在 `settings.xml` 写 `<w:updateFields w:val="true"/>`，Word 打开时会提示“是否更新域”，选“是”即生成/刷新目录页码。
- **标题样式**：使用 Word 内置 `Heading 1/2/3`（而非自定义样式名），TOC 才能抓到；一级标题 `page_break_before`，因此每章自动起新页（节内首个一级标题除外，避免目录后出现空白页）。
- **三线表**：`tblBorders` 只保留 top(1.5pt)/bottom(1.5pt)/insideH(1pt)，再加表头行下框线 1pt；无竖线。表题统一提到表格**上方**（源 md 里题注写在表前或表后都能识别），居中加粗五号，并 `keep_with_next` 防跨页分离。
- **列宽自适应**：按内容显示宽度（中文 2.0em / 英文 1.05em）加权分配，并保证每个单元格不可断词的最小宽度；列数 > 5 时自动降字号（10.5 → 9 → 8pt），列数 > 6 时收窄单元格边距，保证宽表不出现“逐字竖排”。
- **代码块**：Consolas 9pt、底色 `#F5F5F5`、左缩进 0.2cm、不首行缩进、保留原始换行与空格。
- **图注**：取 Markdown 的 alt 文本（`![图 1-1 现状架构](figures/fig-01-current-arch.png)`），置于图片下方居中五号加粗；图片固定 15cm 宽居中。
- **缺图**：不静默跳过，画灰色占位框 + 红色“【缺少图片】”告警，并在控制台打印 `[缺图]` 清单。
- **引号净化**：源 md 中的 ASCII 直引号成对转成中文弯引号 `“”`（跳过行内代码与围栏代码块）。

---

## 6. 目视验收工具（`work/tools/`）

| 工具 | 用法 |
| --- | --- |
| `word2pdf.vbs` | `cscript //nologo work/tools/word2pdf.vbs <docx> <pdf>`，用 Word COM 更新所有域（含 TOC）后导出 PDF |
| `xlsx2pdf.vbs` | `cscript //nologo work/tools/xlsx2pdf.vbs <xlsx> <pdf>`，用 Excel COM 导出 PDF |
| `pdf2png.py` | `python work/tools/pdf2png.py <pdf> 1-6 <outdir> [text]`，按页渲染 PNG（110dpi）或输出文本 |
| `find_pages.py` | `python work/tools/find_pages.py <pdf> 关键字…`，定位关键字所在页 |
| `inspect_docx.py` | 打印标题样式/字号/加粗、缩进、表格 XML，用于核对格式 |

**注意**：`word2pdf.vbs` / `xlsx2pdf.vbs` 结束后必须杀掉残留进程，否则文件被锁、下次构建报 `PermissionError: [Errno 13]`：

```bash
MSYS2_ARG_CONV_EXCL='*' cmd.exe /c "taskkill /F /IM WINWORD.EXE"
MSYS2_ARG_CONV_EXCL='*' cmd.exe /c "taskkill /F /IM EXCEL.EXE"
```

（注意用 `MSYS2_ARG_CONV_EXCL='*'`，否则 MSYS 会把 `/F` 当路径转换报 `Invalid argument`。）

---

## 7. 常见问题

**Q1：Chrome 渲染报错 / PNG 是空白或只有白边**
Chrome 路径必须正确（本机为 `C:/Program Files/Google/Chrome/Application/chrome.exe`）。若机器上没有 Chrome，改 `figlib.py` 里的 `CHROME` 常量。注意 `--screenshot` 输出路径要写成 Windows 盘符路径，HTML 用 `file:///F:/...` 形式。
另外 `--window-size` 的高度必须 ≥ HTML 内容高度，否则底部内容被裁（本库每张图单独指定高度，高度写小了就调大）。

**Q2：图中中文变成方框 / 字重不对**
字体统一用 `Microsoft YaHei`。若在非中文系统上构建，需要装微软雅黑或改 `figlib.py` 的字体族（建议同时保留 `Segoe UI` 兜底）。

**Q3：Word 打开提示“需更新域”**
正常现象。选“是”或全选后 `F9` 更新即可。若目录为空，说明更新域没执行（用 `word2pdf.vbs` 导出 PDF 时会自动更新，可用于核对最终页码）。若想彻底去掉提示，可把 `settings.xml` 的 `updateFields` 改为 `false`，但那样目录需要手工刷新。

**Q4：表格列宽仍然过窄 / 文字竖排**
`build_docx.py` 的 `Builder.table` 里有 `cjk_cm` / `asc_cm` / `mins` 三个常量。两字表头（如“必填”“密级”）被压成竖排时，把 `mins` 的下限从 1.45cm 抬到 1.6cm 即可，代价是长列表格整体变紧。

**Q5：报 `[缺图]`**
说明 md 里引用的 `figures/xxx.png` 不存在或文件名拼错。核对 `STYLE.md` 第 7 节的固定文件名，重跑 `render_figures.py`。

**Q6：构建时报 `PermissionError: [Errno 13]`**
docx/xlsx 正被 Word/Excel 打开，或上次导出的 WINWORD.EXE/EXCEL.EXE 没退出。关掉文件并执行上面的 `taskkill`。

**Q7：`ops_bash` 偶发 `EXECUTOR_UNAVAILABLE`**
MSYS 子进程链接失败的偶发问题，重试一次通常即可。

---

## 8. 修改约定

- 只改 `deliverables/docs/*.md` 的**内容**，不要改动构建器依赖的结构约定：标题必须用 `#`/`##`/`###`；表题必须是独立一行的 `**表 x-y 名称**`；图片必须是独立一行的 `![图 x-y 名称](figures/fig-XX.png)`；清单项用 `- [ ]`。
- 图表编号与文件名**一一绑定**，新增图要与 `STYLE.md` 第 7 节同步，否则编号会乱。
- 改完 md 后必须重跑 `build_docx.py`，并再扫一遍 PDF 目视验收（尤其三线表宽列与图片分页）。

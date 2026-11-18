# -*- coding: utf-8 -*-
"""生成 deliverables/重构实施计划.xlsx（WBS / 甘特 / 风险登记册）。

数据来源：deliverables/docs/09_重构实施计划.md
  表 9-3 五阶段与人天分配（8/11/19/13/12 + 2 缓冲 = 65 人天，13 周）
  表 9-4 里程碑 M1–M5
  表 9-5 WBS 明细（T1.1–T5.4，20 项）
  表 9-7 风险登记册（R1–R10）
运行：work/pyenv/Scripts/python.exe deliverables/docgen/make_xlsx.py
"""
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = r"F:\毕业设计\deliverables\重构实施计划.xlsx"

NAVY = "1F3A5F"
NAVY_L = "2E5580"
ORANGE = "D97706"
BLUE_FILL = "E9F0F8"
ORANGE_FILL = "FDEBD3"
GRAY_FILL = "F2F3F5"
GRAY = "6B7280"

THIN = Side(style="thin", color="D3D8DF")
MED = Side(style="medium", color=NAVY)
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

F_TITLE = Font(name="微软雅黑", size=14, bold=True, color="FFFFFF")
F_HEAD = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
F_BODY = Font(name="微软雅黑", size=9.5, color="1F2937")
F_BOLD = Font(name="微软雅黑", size=9.5, bold=True, color=NAVY)
F_SMALL = Font(name="微软雅黑", size=8.5, color=GRAY)
FILL_HEAD = PatternFill("solid", fgColor=NAVY)
FILL_BAND = PatternFill("solid", fgColor=BLUE_FILL)
FILL_GRAY = PatternFill("solid", fgColor=GRAY_FILL)
FILL_ORANGE = PatternFill("solid", fgColor=ORANGE)
FILL_ORANGE_L = PatternFill("solid", fgColor=ORANGE_FILL)
FILL_NAVY = PatternFill("solid", fgColor=NAVY)
FILL_NAVY_L = PatternFill("solid", fgColor=NAVY_L)

# ---------------------------------------------------------------- 数据
PHASES = [
    # 代号, 周次文本, 起周, 止周, 主题, 主要产出, 人天
    ("P0", "第 1–2 周", 1, 2, "立项与基线", "源码归档、依赖锁定、150 条 golden set、环境就绪", 8),
    ("P1", "第 3–4 周", 3, 4, "骨架与认证", "FastAPI 骨架、10 表迁移、认证授权闭环、前端 API 层", 11),
    ("P2", "第 5–7 周", 5, 7, "领域下沉与 AI 网关", "规则/评分/危机移植、AI 网关、四链路、会话服务", 19),
    ("P3", "第 8–10 周", 8, 10, "部署与可观测", "Compose/K8s、CI/CD、四件套监控、安全加固、压测", 13),
    ("P4", "第 11–13 周", 11, 13, "灰度上线与验收", "三档切量、数据迁移、验收测试、答辩材料", 12),
]

MILESTONES = [
    ("M1", "基线就绪", 2, "原系统可在干净机器一键启动；golden set 150 条入库且标注完成；源码与依赖已归档；CI 空跑通过"),
    ("M2", "登录闭环", 4, "登录/刷新/游客/me 四接口通过测试；10 表迁移可在空库执行；前端可带 token 调通 /api/v1；健康与指标端点可访问"),
    ("M3", "领域一致", 7, "评分与判定一致率 ≥ 99%；四链路降级路径全部验证；legacy 兼容层可承接旧请求；5% 灰度观察 48 小时无 P0"),
    ("M4", "生产就绪", 10, "staging 全栈一键起；CI/CD 全链通过（lint/test/build/scan/deploy）；100 RPS 压测 P95 达标；告警触发演练通过"),
    ("M5", "验收通过", 13, "100% 流量、连续 7 天 SLO 达标；Go-NoGo 清单全绿；文档与代码一致；答辩演示脚本彩排通过"),
]

# 编号, 阶段, 任务名, 产出物, 前置, 人天, 周次, 负责人, 验收标准
WBS = [
    ("T1.1", "P0", "冻结现状基线", "归档包、依赖锁、启动说明", "—", 3, "W1", "Lead", "干净机器可复现启动"),
    ("T1.2", "P0", "建立 golden set", "150 条样本与标注", "T1.1", 3, "W1–W2", "analyst", "双人标注一致率 ≥ 95%"),
    ("T1.3", "P0", "仓库与环境", "monorepo、CI 骨架、venv/镜像", "T1.1", 2, "W2", "Lead", "CI 空跑绿"),
    ("T2.1", "P1", "FastAPI 骨架", "配置/日志/中间件/错误码/探针", "T1.3", 3, "W3", "backend", "冒烟测试通过"),
    ("T2.2", "P1", "数据库与迁移", "Alembic 0001、10 表、种子数据", "T2.1", 3, "W3", "backend", "空库可迁移可回滚"),
    ("T2.3", "P1", "认证与 RBAC", "登录/刷新/游客/me、撤销", "T2.2", 3, "W4", "backend", "越权测试全拦截"),
    ("T2.4", "P1", "前端 API 层", "基址、Bearer、401 刷新", "T2.1", 2, "W4", "backend", "登录态端到端可用"),
    ("T3.1", "P2", "规则/评分/危机移植", "domain 模块 + 回归报告", "T1.2、T2.2", 6, "W5–W6", "backend", "一致率 ≥ 99%"),
    ("T3.2", "P2", "AI 网关", "Provider/熔断/缓存/配额/审计", "T2.1", 5, "W5–W6", "backend", "六类降级路径测试通过"),
    ("T3.3", "P2", "四链路迁移", "v1 接口 + legacy 兼容层", "T3.2", 4, "W6–W7", "backend", "新旧响应结构等价"),
    ("T3.4", "P2", "会话与统计服务", "sessions/turns/score/finish/debrief/stats", "T3.1", 4, "W7", "backend", "幂等与状态机测试通过"),
    ("T4.1", "P3", "容器化", "Dockerfile、Compose 全栈", "T3.x", 2, "W8", "devops", "一键起全栈"),
    ("T4.2", "P3", "编排与 CI/CD", "K8s 清单、镜像流水线", "T4.1", 3, "W8–W9", "devops", "流水线可发布 staging"),
    ("T4.3", "P3", "可观测", "指标/日志/追踪/告警/看板", "T4.1", 4, "W9", "devops", "告警演练触发成功"),
    ("T4.4", "P3", "安全加固", "CSP、限流、审计、自测报告", "T3.3", 2, "W9–W10", "devops", "高危项零残留"),
    ("T4.5", "P3", "性能压测", "k6 脚本、压测报告", "T4.2", 2, "W10", "devops", "100 RPS、P95 达标"),
    ("T5.1", "P4", "三档切量", "切量记录与指标截图", "M4", 3, "W11", "Lead", "100% 流量稳定 7 天"),
    ("T5.2", "P4", "数据迁移回填", "localStorage→PG 迁移脚本与报告", "T3.4", 3, "W11–W12", "backend", "抽样校验一致率 100%"),
    ("T5.3", "P4", "验收测试", "验收报告、缺陷清单", "M4", 3, "W12", "Lead", "P0/P1 缺陷清零"),
    ("T5.4", "P4", "答辩材料", "演示脚本、录屏、讲稿", "T5.1", 3, "W13", "docsmith", "彩排一次通过"),
]

BUFFER = ("—", "—", "缓冲（返工与意外）", "机动", "—", 2, "W1–W13", "Lead", "不占用计划工期，按实际消耗")

# 编号, 风险描述, 类别, 概率, 影响, 等级, 应对措施, 触发信号, 责任人, 复查周期
RISKS = [
    ("R1", "评分口径移植不一致，成绩失真", "技术·一致性", "高", "高", "P0",
     "golden set 前置、双人标注、逐维度归因", "一致率 < 99%", "backend", "每日"),
    ("R2", "单人 13 周工期不足", "进度", "中", "高", "P0",
     "范围分级（核心/一期/二期）、每周燃尽检查", "连续两周落后 > 2 天", "Lead", "每周"),
    ("R3", "AI 供应商限流或涨价", "供应商", "中", "中", "P1",
     "网关可切供应商、缓存命中率优化、规则兜底", "429 比例 > 5%", "backend", "每周"),
    ("R4", "Supabase/localStorage 历史数据迁移丢失", "数据", "中", "高", "P1",
     "双写过渡、迁移前后抽样校验、保留 30 天只读快照", "抽样不一致", "backend", "每里程碑"),
    ("R5", "危机拦截被绕过引发伦理事故", "合规·伦理", "低", "极高", "P0",
     "服务端硬拦截 + 审计告警 + 上线前红队测试", "审计日志出现 crisis 但 used_ai=true", "Lead", "每周"),
    ("R6", "K8s 环境不可用（答辩现场网络受限）", "环境", "中", "中", "P1",
     "Compose 离线方案常备、本地镜像缓存", "现场拉镜像失败", "devops", "每里程碑"),
    ("R7", "前端改造引入回归（749 行 TrainingPage）", "工程·回归", "中", "中", "P1",
     "先加 E2E 再改、按页面灰度、保留旧调用开关", "E2E 连续失败", "backend", "每次合并"),
    ("R8", "依赖漏洞或供应链风险", "供应链", "中", "中", "P2",
     "依赖锁定、Trivy 门禁、每周升级窗口", "扫描出 HIGH", "devops", "每周"),
    ("R9", "文档与代码脱节，答辩被质疑", "文档", "中", "中", "P1",
     "附录A 由 OpenAPI 生成、文档随 PR 更新", "文档评审发现不一致", "docsmith", "每里程碑"),
    ("R10", "压测发现 P95 不达标", "性能", "中", "中", "P1",
     "索引与连接池预案、读写分离预案", "压测报告超标", "devops", "每里程碑"),
]


def weeks_of(text):
    """'W1–W2' -> [1,2];  'W7' -> [7]"""
    nums = [int(x) for x in re.findall(r"W(\d+)", text)]
    if not nums:
        return []
    if len(nums) == 1:
        return nums
    return list(range(nums[0], nums[1] + 1))


# ---------------------------------------------------------------- Sheet1 WBS
def sheet_wbs(wb):
    ws = wb.active
    ws.title = "WBS"
    ws.sheet_view.showGridLines = False

    cols = [("阶段", 7), ("任务编号", 10), ("任务名", 24), ("产出物", 34),
            ("前置依赖", 12), ("工时(人天)", 10), ("起止周", 11), ("负责人", 11),
            ("验收标准", 30)]
    ncol = len(cols)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(row=1, column=1, value="叩门 AI 陪练舱 · 生产化改造 WBS（13 周 5 阶段 / 65 人天，对应文档表 9-3·表 9-5）")
    c.font = F_TITLE
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    c = ws.cell(row=2, column=1, value="负责人为角色名（Lead / analyst / backend / devops / docsmith）；人天合计 65，含 2 人天缓冲。数据与 docs/09_重构实施计划.md 表 9-5 逐行一致。")
    c.font = F_SMALL
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 26

    hr = 3
    for i, (name, w) in enumerate(cols, start=1):
        c = ws.cell(row=hr, column=i, value=name)
        c.font = F_HEAD
        c.fill = FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(left=THIN, right=THIN, top=THIN, bottom=MED)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[hr].height = 26

    rows = [(t,) + tuple(x for x in t[1:]) for t in []]
    body = [(w[1], w[0], w[2], w[3], w[4], w[5], w[6], w[7], w[8]) for w in WBS]
    body.append((BUFFER[1], BUFFER[0], BUFFER[2], BUFFER[3], BUFFER[4], BUFFER[5],
                 BUFFER[6], BUFFER[7], BUFFER[8]))

    r = hr + 1
    prev_phase = None
    for row in body:
        phase = row[0]
        for i, v in enumerate(row, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font = F_BODY
            c.border = BOX
            if i == 1:
                c.alignment = Alignment(horizontal="center", vertical="center")
                c.font = F_BOLD
            elif i in (2,):
                c.alignment = Alignment(horizontal="center", vertical="center")
                c.font = Font(name="微软雅黑", size=9.5, bold=True, color=NAVY)
            elif i in (5, 6, 7, 8):
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        if phase in ("P0", "P2", "P4"):
            for i in range(1, ncol + 1):
                ws.cell(row=r, column=i).fill = FILL_BAND
        ws.row_dimensions[r].height = 30
        prev_phase = phase
        r += 1

    # 合计行
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    c = ws.cell(row=r, column=1, value="合计（5 阶段 20 项任务 + 缓冲）")
    c.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="right", vertical="center")
    total = sum(w[5] for w in WBS) + BUFFER[5]
    c = ws.cell(row=r, column=6, value=total)
    c.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="center", vertical="center")
    c = ws.cell(row=r, column=7, value="13 周")
    c.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=r, start_column=8, end_row=r, end_column=9)
    c = ws.cell(row=r, column=8, value="按 5 阶段硬门禁推进，未过门禁不进入下一阶段")
    c.font = Font(name="微软雅黑", size=9, bold=True, color="FFFFFF")
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[r].height = 24

    ws.freeze_panes = "C4"
    ws.auto_filter.ref = f"A{hr}:{get_column_letter(ncol)}{hr + len(body)}"
    ws.print_title_rows = f"{hr}:{hr}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


# ---------------------------------------------------------------- Sheet2 甘特
def sheet_gantt(wb):
    ws = wb.create_sheet("甘特")
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90

    first_week_col = 4          # A阶段 B任务 C人天 D.. W1..W13
    last_week_col = first_week_col + 12
    ncol = last_week_col

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(row=1, column=1, value="13 周实施甘特（深蓝=计划  ·  橙=里程碑  ·  浅蓝=阶段带）")
    c.font = F_TITLE
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    # 图例（单行富文本，色块符号与列宽无关，避免与表头错位）
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    c = ws.cell(row=2, column=1)
    try:
        from openpyxl.cell.rich_text import CellRichText, TextBlock
        from openpyxl.cell.text import InlineFont
        c.value = CellRichText([
            TextBlock(InlineFont(rFont="微软雅黑", sz=9, b=True, color=GRAY), "图例：" ),
            TextBlock(InlineFont(rFont="微软雅黑", sz=10, b=True, color=NAVY), "■ 计划任务"),
            TextBlock(InlineFont(rFont="微软雅黑", sz=9, color=GRAY), "　"),
            TextBlock(InlineFont(rFont="微软雅黑", sz=10, b=True, color=ORANGE), "■ 里程碑"),
            TextBlock(InlineFont(rFont="微软雅黑", sz=9, color=GRAY), "　"),
            TextBlock(InlineFont(rFont="微软雅黑", sz=10, b=True, color="A8BDD4"), "■ 阶段带"),
            TextBlock(InlineFont(rFont="微软雅黑", sz=9, color=GRAY), "　　（周次列自 W1 起，任务条覆盖起止周区间）"),
        ])
    except Exception:
        c.value = "图例：■ 计划任务（深蓝）  ■ 里程碑（橙）  ■ 阶段带（浅蓝）"
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 20

    hr = 3
    heads = ["阶段", "任务 / 里程碑", "人天"] + [f"W{i}" for i in range(1, 14)]
    for i, name in enumerate(heads, start=1):
        c = ws.cell(row=hr, column=i, value=name)
        c.font = F_HEAD
        c.fill = FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(left=THIN, right=THIN, top=THIN, bottom=MED)
    ws.row_dimensions[hr].height = 24

    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 8
    for i in range(1, 14):
        ws.column_dimensions[get_column_letter(first_week_col + i - 1)].width = 5.2

    r = hr + 1
    # 阶段带
    for code, wtxt, w0, w1, theme, out, days in PHASES:
        ws.cell(row=r, column=1, value=code).font = F_BOLD
        ws.cell(row=r, column=1).alignment = Alignment(horizontal="center", vertical="center")
        c = ws.cell(row=r, column=2, value=f"{theme}（{wtxt}）")
        c.font = Font(name="微软雅黑", size=9.5, bold=True, color=NAVY)
        c.alignment = Alignment(horizontal="left", vertical="center")
        c = ws.cell(row=r, column=3, value=days)
        c.font = F_BODY
        c.alignment = Alignment(horizontal="center", vertical="center")
        for wk in range(w0, w1 + 1):
            c = ws.cell(row=r, column=first_week_col + wk - 1)
            c.fill = FILL_BAND
            c.border = Border(top=THIN, bottom=THIN)
        for cn in (1, 2, 3):
            ws.cell(row=r, column=cn).border = BOX
        ws.row_dimensions[r].height = 20
        r += 1

    # 任务条
    for t in WBS:
        num, phase, name, out, pre, days, wtxt, owner, acc = t
        ws.cell(row=r, column=1, value=phase).font = F_BODY
        ws.cell(row=r, column=1).alignment = Alignment(horizontal="center", vertical="center")
        c = ws.cell(row=r, column=2, value=f"{num} {name}")
        c.font = F_BODY
        c.alignment = Alignment(horizontal="left", vertical="center")
        c = ws.cell(row=r, column=3, value=days)
        c.font = F_BODY
        c.alignment = Alignment(horizontal="center", vertical="center")
        for wk in weeks_of(wtxt):
            c = ws.cell(row=r, column=first_week_col + wk - 1)
            c.fill = FILL_NAVY
            c.border = Border(top=THIN, bottom=THIN)
        for cn in (1, 2, 3):
            ws.cell(row=r, column=cn).border = BOX
        ws.row_dimensions[r].height = 19
        r += 1

    # 缓冲
    ws.cell(row=r, column=1, value="—").font = F_BODY
    ws.cell(row=r, column=1).alignment = Alignment(horizontal="center", vertical="center")
    c = ws.cell(row=r, column=2, value="缓冲（返工与意外，2 人天）")
    c.font = Font(name="微软雅黑", size=9.5, italic=True, color=GRAY)
    c.alignment = Alignment(horizontal="left", vertical="center")
    c = ws.cell(row=r, column=3, value=2)
    c.font = F_BODY
    c.alignment = Alignment(horizontal="center", vertical="center")
    for wk in range(1, 14):
        c = ws.cell(row=r, column=first_week_col + wk - 1)
        c.fill = FILL_GRAY
        c.border = Border(top=THIN, bottom=THIN)
    for cn in (1, 2, 3):
        ws.cell(row=r, column=cn).border = BOX
    ws.row_dimensions[r].height = 19
    r += 2

    # 里程碑行
    c = ws.cell(row=r, column=1, value="里程碑")
    c.font = Font(name="微软雅黑", size=9.5, bold=True, color="FFFFFF")
    c.fill = FILL_ORANGE
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    ws.cell(row=r, column=1, value="里程碑 M1–M5（准出条件见文档表 9-4）").font = Font(
        name="微软雅黑", size=9.5, bold=True, color="FFFFFF")
    ws.cell(row=r, column=1).fill = FILL_ORANGE
    ws.cell(row=r, column=1).alignment = Alignment(horizontal="center", vertical="center")
    for i in range(4, ncol + 1):
        ws.cell(row=r, column=i).fill = FILL_ORANGE
        ws.cell(row=r, column=i).border = BOX
    ws.row_dimensions[r].height = 20
    r += 1

    for code, label, wk, cond in MILESTONES:
        c = ws.cell(row=r, column=1, value=code)
        c.font = F_BOLD
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        ws.cell(row=r, column=1, value=f"{code} {label}（第 {wk} 周末）").font = F_BOLD
        ws.cell(row=r, column=1).alignment = Alignment(horizontal="left", vertical="center")
        c = ws.cell(row=r, column=3, value="◆")
        c.font = Font(name="微软雅黑", size=9, bold=True, color=ORANGE)
        c.alignment = Alignment(horizontal="center", vertical="center")
        for i in range(4, ncol + 1):
            ws.cell(row=r, column=i).border = Border(top=THIN, bottom=THIN)
        c = ws.cell(row=r, column=first_week_col + wk - 1, value="◆")
        c.fill = FILL_ORANGE
        c.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.comment = None
        ws.row_dimensions[r].height = 19
        r += 1

    ws.freeze_panes = "D4"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


# ---------------------------------------------------------------- Sheet3 风险
def sheet_risk(wb):
    ws = wb.create_sheet("风险登记册")
    ws.sheet_view.showGridLines = False

    cols = [("编号", 7), ("风险描述", 38), ("类别", 13), ("概率", 7), ("影响", 7),
            ("等级", 8), ("应对措施", 38), ("触发信号", 24), ("责任人", 10), ("复查周期", 11)]
    ncol = len(cols)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(row=1, column=1, value="风险登记册（R1–R10，对应文档表 9-7）")
    c.font = F_TITLE
    c.fill = FILL_HEAD
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    c = ws.cell(row=2, column=1, value="等级口径：P0 = 阻断交付，须当周消除；P1 = 影响里程碑，须有预案；P2 = 可接受但需跟踪。复查周期为每周例会核对。")
    c.font = F_SMALL
    c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 24

    hr = 3
    for i, (name, w) in enumerate(cols, start=1):
        c = ws.cell(row=hr, column=i, value=name)
        c.font = F_HEAD
        c.fill = FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(left=THIN, right=THIN, top=THIN, bottom=MED)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[hr].height = 26

    level_fill = {"P0": "F8C8B4", "P1": "FCE0B6", "P2": "E3E7EC"}
    r = hr + 1
    for risk in RISKS:
        for i, v in enumerate(risk, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font = F_BODY
            c.border = BOX
            if i in (1, 4, 5, 6, 9, 10):
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.cell(row=r, column=1).font = Font(name="微软雅黑", size=9.5, bold=True, color=NAVY)
        lv = risk[5]
        cl = ws.cell(row=r, column=6)
        cl.fill = PatternFill("solid", fgColor=level_fill.get(lv, "FFFFFF"))
        cl.font = Font(name="微软雅黑", size=10, bold=True, color="1F2937" if lv != "P0" else "9B2C1B")
        ws.row_dimensions[r].height = 34
        r += 1

    # 等级数据校验
    dv = DataValidation(type="list", formula1='"P0,P1,P2"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"F{hr + 1}:F{hr + len(RISKS)}")

    ws.freeze_panes = "C4"
    ws.auto_filter.ref = f"A{hr}:{get_column_letter(ncol)}{hr + len(RISKS)}"
    ws.print_title_rows = f"{hr}:{hr}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


def main():
    wb = Workbook()
    sheet_wbs(wb)
    sheet_gantt(wb)
    sheet_risk(wb)
    wb.properties.title = "叩门 AI 陪练舱 · 重构实施计划"
    wb.properties.creator = "docsmith"
    wb.properties.subject = "13 周 5 阶段 WBS / 甘特 / 风险登记册"
    wb.active = 0
    wb.save(OUT)

    # 自检
    from openpyxl import load_workbook
    wb2 = load_workbook(OUT)
    print(f"[已生成] {OUT}")
    for ws in wb2.worksheets:
        filled = sum(1 for row in ws.iter_rows() for c in row
                     if c.fill is not None and c.fill.fgColor.rgb not in (None, "00000000"))
        print(f"  {ws.title}: {ws.max_row} 行 × {ws.max_column} 列 · 着色单元格 {filled}")
    ws = wb2["WBS"]
    task_days = sum(ws.cell(row=r, column=6).value or 0 for r in range(4, 24)
                    if isinstance(ws.cell(row=r, column=6).value, int))
    buf = ws.cell(row=24, column=6).value
    total = ws.cell(row=25, column=6).value
    print(f"  WBS 人天：20 项任务 {task_days} + 缓冲 {buf} = {task_days + buf}（表内合计 {total}）")
    assert task_days + buf == total == 65, "人天合计与表 9-3 不一致"


if __name__ == "__main__":
    main()

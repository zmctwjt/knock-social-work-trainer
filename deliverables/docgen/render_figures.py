# -*- coding: utf-8 -*-
"""生成 7 张出版级配图：Python 拼 SVG -> Chrome 无头渲染 -> Pillow 裁白边/缩放 1600。

用法:
    python render_figures.py            # 全部
    python render_figures.py 1 4        # 只渲染 fig-01、fig-04
"""
import sys
from pathlib import Path

from figlib import (
    Fig, render, NAVY, NAVY2, NAVY3, BLUE_FILL, BLUE_BORDER, BLUE_SOFT,
    ORANGE, ORANGE_FILL, ORANGE_BORDER, ORANGE_SOFT, GRAY, GRAY_FILL,
    GRAY_BORDER, TEXT, TEXT2, WHITE,
)

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "deliverables" / "figures"

N = "font-weight:700"  # 占位，不使用


# ================================================================ 图 1 现状架构
def fig01():
    f = Fig(1500, 800)

    # 浏览器
    f.rect(40, 40, 430, 420, fill=BLUE_SOFT, stroke=NAVY, sw=2)
    f.txt(255, 74, "浏览器（React 18 SPA）", size=17, color=NAVY, weight="700")
    f.txt(255, 98, "dist/ 静态产物 · 11 个页面", size=13, color=GRAY)
    f.block(60, 112, 390, 58, "训练页 / 复盘页 / 记录页", [], fill=WHITE, stroke=BLUE_BORDER,
            title_size=15, body_size=13)
    f.block(60, 184, 390, 120, "业务逻辑全部在前端", [
        "规则判定 568 行 · 对话引擎 567 行",
        "六维评分 522 行 · 危机拦截 199 行",
        "综合分 = 规则底分×0.4 + AI 评分×0.6",
    ], fill=WHITE, stroke=BLUE_BORDER, title_size=15, body_size=13)
    f.block(60, 318, 390, 104, "localStorage 为默认权威存储", [
        "knock.records / settings / draft / sessions",
        "debriefs / heat / nick / tourDone …（9 类键）",
    ], fill=WHITE, stroke=BLUE_BORDER, title_size=15, body_size=13)
    f.txt(255, 447, "成绩由前端计算，换设备或清缓存即丢失", size=12.5, color=ORANGE, weight="700")

    # Node 单进程
    f.rect(570, 40, 460, 420, fill="#FFFFFF", stroke=NAVY, sw=2)
    f.txt(800, 74, "Node 单进程 · node:http", size=17, color=NAVY, weight="700")
    f.txt(800, 98, "端口 8787 · 零第三方依赖 · 无副本", size=13, color=GRAY)
    f.block(590, 112, 420, 58, "静态托管 + SPA fallback", ["同进程托管 dist/ · 请求体上限 512 KB"],
            fill=WHITE, stroke=BLUE_BORDER, title_size=15, body_size=13)
    f.block(590, 184, 420, 120, "4 条 AI 代理链路", [
        "POST /api/ai/intent · persona",
        "POST /api/ai/score · debrief",
        "密钥在服务端环境变量，浏览器不接触",
    ], fill=WHITE, stroke=BLUE_BORDER, title_size=15, body_size=13)
    f.block(590, 318, 420, 104, "进程内治理（内存态）", [
        "限流 20 次/分/IP · 并发 2 · 日上限 800",
        "缓存 300 条 / TTL 10 min · 重启清零",
    ], fill=WHITE, stroke=BLUE_BORDER, title_size=15, body_size=13)
    f.txt(800, 447, "单点：进程不可用即全站不可用", size=12.5, color=ORANGE, weight="700")

    # GLM
    f.block(1110, 150, 340, 200, "智谱开放平台", [
        "主模型 glm-4.7-flash",
        "降级 glm-4.5-flash → glm-4-flash",
        "关闭思维链 · 单次超时 45 s",
    ], fill=ORANGE_SOFT, stroke=ORANGE_BORDER, title_size=16, body_size=13)

    # 连线
    f.arrow([(470, 250), (570, 250)], both=True)
    f.txt(520, 240, "HTTP", size=11.5, color=NAVY, weight="700")
    f.txt(520, 268, "/api/ai/*", size=11.5, color=GRAY)
    f.arrow([(1030, 250), (1110, 250)])
    f.txt(1070, 238, "HTTPS", size=11.5, color=GRAY)

    # Supabase 可选
    f.rect(40, 560, 470, 120, fill=GRAY_FILL, stroke=GRAY_BORDER, sw=1.6, dash="7 5")
    f.txt(275, 592, "Supabase（可选，默认未启用）", size=15, color="#4B5563", weight="700")
    f.txt(275, 622, "7 张表 · 5 个视图 · 9 个索引", size=13, color=GRAY)
    f.txt(275, 648, "RLS 全放行（6 表启用 / 桥表未启用）· 匿名 key · 无 Auth", size=12, color=GRAY)
    f.arrow([(255, 460), (255, 560)], color=GRAY, dash="6 5")
    f.label(255, 512, "可选直连（未启用）", size=12, color=GRAY)

    # 现状概要
    f.rect(570, 560, 460, 120, fill="#FFFFFF", stroke=GRAY_BORDER, sw=1.4, dash="5 4")
    f.txt(800, 592, "工程形态概要", size=14, color=NAVY, weight="700")
    f.txt(800, 620, "后端 1,046 行 / 前端 12,893 行", size=12.5, color=TEXT2)
    f.txt(800, 646, "无测试 · 无容器 · 无监控 · 无 CI", size=12.5, color=TEXT2)

    # 三个问题徽标
    probs = [
        ("① 单点：进程无副本", "服务不可用即全站不可用，重启清空配额与缓存"),
        ("② 无鉴权：API 无身份校验", "CORS 白名单仅放行本机，任何人可直连代理"),
        ("③ 数据在浏览器：成绩可篡改", "localStorage 为权威存储，前端计算并保存分数"),
    ]
    for i, (h1, h2) in enumerate(probs):
        x = 40 + i * 490
        f.rect(x, 700, 440, 76, fill=ORANGE_FILL, stroke=ORANGE_BORDER, sw=1.6)
        f.rect(x, 700, 5, 76, fill=ORANGE, stroke=ORANGE, sw=0, rx=2)
        f.txt(x + 24, 730, h1, size=14, color=NAVY, weight="700", anchor="start")
        f.txt(x + 24, 756, h2, size=12.5, color=TEXT2, anchor="start")
    return f


# ================================================================ 图 2 目标架构
def fig02():
    f = Fig(1500, 780)
    bands = [
        (40, 90, "接入层"),
        (160, 140, "应用层"),
        (330, 120, "领域层"),
        (480, 130, "数据层"),
        (640, 90, "外部服务"),
    ]
    for y, h, name in bands:
        f.rect(164, y, 1016, h, fill=BLUE_SOFT, stroke=BLUE_BORDER, sw=1.4, dash="7 5")
        f.rect(24, y + h / 2 - 30, 126, 60, fill=NAVY, stroke=NAVY, sw=0)
        f.txt(87, y + h / 2 + 6, name, size=16, color=WHITE, weight="700")

    # 接入层
    items1 = [
        ("CDN · 静态资源", "dist/ 上 CDN"),
        ("WAF · 攻击防护", "DDoS / 注入"),
        ("Nginx Ingress", "TLS 终止 · /api/v1 路由"),
        ("灰度 / 限流", "权重切量 · 边缘限流"),
    ]
    for i, (t, s) in enumerate(items1):
        f.block(180 + i * 250, 58, 234, 62, t, [s], title_size=14, body_size=12)

    # 应用层
    items2 = [
        ("认证与 RBAC", ["JWT 签发 / 刷新", "学生·教师·管理员"]),
        ("会话服务", ["建会话 / 回合推进", "幂等状态机"]),
        ("评分服务", ["六维汇总与落库", "规则+AI 双算"]),
        ("AI 网关", ["缓存·熔断·配额", "供应商切换·审计"]),
        ("复盘与统计", ["复盘报告", "班级/个人统计"]),
    ]
    for i, (t, ls) in enumerate(items2):
        f.block(180 + i * 202, 180, 192, 110, t, ls, title_size=14, body_size=12)

    # 领域层
    items3 = [
        ("规则引擎", ["162 判定词 + 8 步"]),
        ("对话引擎", ["118 节点白名单"]),
        ("六维评分", ["25/20/15/20/10/10"]),
        ("危机拦截", ["三级硬拦截", "永不调用模型"]),
        ("内容资产", ["12 角色 · 19 技巧卡"]),
    ]
    for i, (t, ls) in enumerate(items3):
        f.block(180 + i * 202, 348, 192, 84, t, ls, title_size=14, body_size=12)

    # 数据层
    items4 = [
        ("MySQL 8.0", ["主从 · 11 张表 · 18 索引", "Alembic 版本化"]),
        ("MySQL Router", ["读写分离路由", "连接复用"]),
        ("Redis 7", ["缓存 / 限流", "配额 / 会话 / 熔断"]),
        ("对象存储 OBS", ["知识卡 / 录播", "备份归档"]),
        ("消息与任务", ["ARQ 异步任务", "重试与死信"]),
    ]
    for i, (t, ls) in enumerate(items4):
        f.block(180 + i * 202, 498, 192, 94, t, ls, title_size=14, body_size=12)

    # 外部
    f.block(180, 658, 984, 60, "智谱 GLM-4.7-Flash", [
        "降级链 glm-4.5-flash → glm-4-flash · 关闭思维链 · 超时 30 s · 出网白名单"
    ], fill=ORANGE_SOFT, stroke=ORANGE_BORDER, title_size=15, body_size=12.5)

    # 层间箭头
    for y1, y2 in [(130, 160), (300, 330), (450, 480), (610, 640)]:
        f.arrow([(672, y1), (672, y2)], sw=2.2)

    # 横切
    f.rect(1210, 40, 260, 690, fill=BLUE_SOFT, stroke=BLUE_BORDER, sw=1.6)
    f.txt(1340, 72, "横切关注点", size=15, color=NAVY, weight="700")
    cross = [
        ("日志", "structlog JSON"),
        ("指标", "prometheus-client"),
        ("追踪", "OpenTelemetry + Tempo"),
        ("审计", "ai_audit_log 落库"),
        ("异常", "Sentry 告警"),
    ]
    for i, (t, s) in enumerate(cross):
        f.block(1226, 96 + i * 120, 228, 100, t, [s], fill=WHITE, stroke=BLUE_BORDER,
                title_size=14, body_size=11.5)

    # 采集总线
    for y in (85, 230, 390, 545, 685):
        f.line([(1180, y), (1197, y)], color=NAVY3, sw=1.4, dash="4 4")
    f.line([(1197, 85), (1197, 685)], color=NAVY3, sw=1.4, dash="4 4")
    f.arrow([(1197, 390), (1210, 390)], color=NAVY3, sw=1.6, dash="4 4")
    return f


# ================================================================ 图 3 部署拓扑
def fig03():
    f = Fig(1500, 700)
    row1 = [
        (10, 180, "用户", ["浏览器 · 移动端", "500 在线"]),
        (230, 180, "CDN + WAF", ["静态资源加速", "DDoS / 注入防护"]),
        (450, 200, "Nginx Ingress", ["TLS 终止（cert-manager）", "/api/v1 路由"]),
        (690, 240, "API Pod × 3", ["FastAPI · HPA 3–10", "无状态 · 滚动发布"]),
        (970, 160, "MySQL Router", ["读写分离路由", "100 连接 → 1,000 会话"]),
        (1170, 320, "MySQL 8.0 主库", ["11 表（10 业务 + 1 令牌撤销）", "18 索引 · 主从复制", "每日全量 + binlog 归档"]),
    ]
    for x, w, t, ls in row1:
        f.block(x, 60, w, 110, t, ls, title_size=15, body_size=12)
    for x in (190, 410, 650, 930, 1130):
        f.arrow([(x, 115), (x + 40, 115)] if x != 1130 else [(x, 115), (x + 40, 115)])

    # 外部模型
    f.block(30, 250, 260, 150, "外部服务：智谱", [
        "GLM-4.7-Flash 主模型",
        "降级 4.5-flash → 4-flash",
        "出网白名单 + 熔断",
    ], fill=ORANGE_SOFT, stroke=ORANGE_BORDER, title_size=15, body_size=12.5)

    # 数据与基础设施
    f.rect(690, 250, 800, 150, fill=BLUE_SOFT, stroke=BLUE_BORDER, sw=1.4, dash="7 5")
    f.txt(710, 276, "数据与基础设施（内网 · 不暴露公网）", size=14, color=NAVY,
          weight="700", anchor="start")
    f.block(710, 290, 220, 95, "Redis 7", ["缓存 / 限流 / 配额 / 会话"], title_size=14, body_size=12)
    f.block(950, 290, 200, 95, "对象存储 OBS", ["知识卡 / 录播 / 备份"], title_size=14, body_size=12)
    f.block(1170, 290, 300, 95, "MySQL 8.0 从库", ["只读查询 · 报表 · 灾备"], title_size=14, body_size=12)

    # 请求链路箭头
    f.arrow([(700, 170), (700, 210), (160, 210), (160, 250)], sw=2)
    f.label(430, 196, "HTTPS 出网（仅模型域名）", size=12, color=NAVY)
    f.arrow([(810, 170), (810, 250)], sw=2)
    f.label(880, 205, "读写 / 缓存", size=12)
    f.arrow([(1400, 170), (1400, 290)], sw=2)
    f.txt(1386, 222, "流复制（异步）", size=12, color=TEXT2, anchor="end")

    # 可观测
    f.rect(30, 470, 670, 180, fill="#FFFFFF", stroke=BLUE_BORDER, sw=1.6, dash="7 5")
    f.txt(365, 500, "可观测与告警（旁挂，不参与请求路径）", size=14, color=NAVY, weight="700")
    for i, name in enumerate(["Prometheus", "Grafana", "Loki", "Tempo", "Sentry"]):
        f.chip(50 + i * 128, 520, name, size=12, w=118, h=52, fill=BLUE_SOFT, stroke=BLUE_BORDER)
    f.txt(365, 610, "8 条告警规则 · SLO 看板 · 日志 30 天 · 追踪采样 10%", size=12, color=GRAY)

    # 备份与交付
    f.rect(730, 470, 760, 180, fill="#FFFFFF", stroke=BLUE_BORDER, sw=1.6, dash="7 5")
    f.txt(1110, 500, "备份与交付", size=14, color=NAVY, weight="700")
    for i, name in enumerate(["每日全量 → OBS", "binlog 归档", "GitHub Actions", "Trivy 扫描", "滚动发布"]):
        f.chip(750 + i * 146, 520, name, size=12, w=136, h=52, fill=BLUE_SOFT, stroke=BLUE_BORDER)
    f.txt(1110, 610, "RPO 15 min / RTO 1 h · 季度灾备演练 · 一键回滚", size=12, color=GRAY)
    return f


# ================================================================ 图 4 ER
def fig04():
    f = Fig(1500, 860)
    tables = {
        "accounts": (60, 70, ["PK id", "email · role", "password_hash", "created_at", "状态 / 最后登录"]),
        "training_records": (60, 270, ["PK id", "FK account_id", "FK scenario_id", "total_score", "duration_sec"]),
        "user_settings": (60, 470, ["PK id", "FK account_id", "theme · ai_ratio", "default_difficulty"]),
        "ai_audit_log": (60, 670, ["PK id", "FK account_id", "chain · request_id", "degraded · tokens"]),
        "training_sessions": (560, 70, ["PK id", "FK account_id", "FK scenario_id", "stage · status", "started_at"]),
        "token_revocations": (560, 670, ["PK id", "FK account_id", "jti · token_type", "revoked_at · expires_at"]),
        "debriefs": (560, 270, ["PK id", "FK session_id", "summary", "suggestions", "generated_at"]),
        "scenarios": (560, 470, ["PK id", "title · difficulty", "stage_count", "crisis_profile"]),
        "turns": (1060, 70, ["PK id", "FK session_id", "speaker · content", "risk_level", "created_at"]),
        "stage_scores": (1060, 270, ["PK id", "FK session_id", "empathy / probing …", "six dimensions 0–100"]),
        "knowledge_cards": (1060, 470, ["PK id", "title · category", "content", "独立内容资产（19 张）", "无外键"]),
    }
    for name, (x, y, fields) in tables.items():
        f.rect(x, y, 300, 140, fill=WHITE, stroke=BLUE_BORDER, sw=1.6)
        f.rect(x, y, 300, 34, fill=NAVY, stroke=NAVY, sw=0, rx=6)
        f.rect(x, y + 20, 300, 14, fill=NAVY, stroke=NAVY, sw=0, rx=0)
        f.txt(x + 150, y + 23, name, size=14, color=WHITE, weight="700")
        for i, fd in enumerate(fields):
            f.txt(x + 16, y + 54 + i * 18, fd, size=11.5, color=TEXT2, anchor="start")

    def rel(pts, label, lx, ly):
        f.arrow(pts, color=NAVY3, sw=1.6)
        f.label(lx, ly, label, size=11.5, color=NAVY2)

    rel([(360, 140), (560, 140)], "1 : N", 460, 128)
    rel([(860, 140), (1060, 140)], "1 : N", 960, 128)
    rel([(660, 210), (660, 270)], "1 : 1", 700, 238)
    rel([(800, 210), (800, 240), (1210, 240), (1210, 270)], "1 : N", 1000, 228)
    rel([(160, 210), (160, 270)], "1 : N", 200, 238)
    rel([(360, 175), (396, 175), (396, 540), (360, 540)], "1 : 1", 396, 352)
    rel([(560, 540), (522, 540), (522, 100), (560, 100)], "1 : N", 522, 470)
    rel([(60, 160), (44, 160), (44, 740), (60, 740)], "1 : N", 44, 640)
    rel([(360, 200), (452, 200), (452, 740), (560, 740)], "1 : N", 500, 726)

    f.txt(760, 838, "PK 主键 · FK 外键 · 1 : N 一对多 · 1 : 1 一对一 · 关系线对应外键约束",
          size=12.5, color=GRAY)
    return f


# ================================================================ 图 5 甘特
def fig05():
    f = Fig(1500, 780)
    x0, colw = 440, 78
    grid_r = x0 + 13 * colw

    def xw(u):
        return x0 + u * colw

    f.txt(30, 48, "阶段 / 任务", size=15, color=NAVY, weight="700", anchor="start")
    for i in range(13):
        f.txt(x0 + (i + 0.5) * colw, 52, f"W{i + 1}", size=12.5, color=NAVY, weight="700")
        if i:
            f.line([(x0 + i * colw, 34), (x0 + i * colw, 690)], color="#E5E7EB", sw=1)
    f.line([(x0, 34), (x0, 690)], color=GRAY_BORDER, sw=1.2)
    f.line([(x0, 34), (grid_r, 34)], color=GRAY_BORDER, sw=1.2)
    f.txt(30, 86, "里程碑", size=13, color=ORANGE, weight="700", anchor="start")
    f.line([(x0, 96), (grid_r, 96)], color="#E5E7EB", sw=1)

    phases = [
        ("P0 立项与基线", "W1–W2 · 8 人天", 0, 2, [
            ("T1.1 冻结现状基线", 0, 1), ("T1.2 建立 golden set", 0, 2), ("T1.3 仓库与环境", 1, 2)]),
        ("P1 骨架与认证", "W3–W4 · 11 人天", 2, 4, [
            ("T2.1 FastAPI 骨架", 2, 3), ("T2.2 数据库与迁移", 2, 3),
            ("T2.3 认证与 RBAC", 3, 4), ("T2.4 前端 API 层", 3, 4)]),
        ("P2 领域下沉与 AI 网关", "W5–W7 · 19 人天", 4, 7, [
            ("T3.1 规则/评分/危机移植", 4, 6), ("T3.2 AI 网关", 4, 6),
            ("T3.3 四链路迁移", 5, 7), ("T3.4 会话与统计服务", 6, 7)]),
        ("P3 部署与可观测", "W8–W10 · 13 人天", 7, 10, [
            ("T4.1 容器化", 7, 8), ("T4.2 编排与 CI/CD", 7, 9), ("T4.3 可观测", 8, 9),
            ("T4.4 安全加固", 8, 10), ("T4.5 性能压测", 9, 10)]),
        ("P4 灰度上线与验收", "W11–W13 · 12 人天", 10, 13, [
            ("T5.1 三档切量", 10, 11), ("T5.2 数据迁移回填", 10, 12),
            ("T5.3 验收测试", 11, 12), ("T5.4 答辩材料", 12, 13)]),
    ]

    y = 106
    for name, meta, u0, u1, tasks in phases:
        f.rect(24, y, 1416, 26, fill=BLUE_SOFT, stroke="none", sw=0, rx=3)
        f.txt(36, y + 18, name, size=14, color=NAVY, weight="700", anchor="start")
        f.txt(300, y + 18, meta, size=11.5, color=GRAY, anchor="start")
        f.rect(xw(u0) + 2, y + 6, (u1 - u0) * colw - 4, 14, fill=NAVY, stroke=NAVY, sw=0, rx=3)
        y += 26
        for tn, a, b in tasks:
            f.txt(54, y + 15, tn, size=12.5, color=TEXT2, anchor="start")
            f.rect(xw(a) + 2, y + 5, max((b - a) * colw - 4, 8), 12, fill=NAVY3, stroke=NAVY3, sw=0, rx=3)
            y += 22
        y += 4

    for i, (u, name) in enumerate([(2, "M1"), (4, "M2"), (7, "M3"), (10, "M4"), (13, "M5")]):
        cx = xw(u)
        f.diamond(cx, 86, 8, fill=ORANGE, stroke=ORANGE)
        f.txt(cx + 13, 90, name, size=11.5, color=ORANGE, weight="700", anchor="start")

    # 图例
    ly = 730
    f.rect(30, ly - 12, 26, 14, fill=NAVY, stroke=NAVY, sw=0, rx=3)
    f.txt(66, ly, "阶段计划", size=12.5, color=TEXT2, anchor="start")
    f.rect(160, ly - 12, 26, 14, fill=NAVY3, stroke=NAVY3, sw=0, rx=3)
    f.txt(196, ly, "任务条", size=12.5, color=TEXT2, anchor="start")
    f.diamond(320, ly - 5, 8, fill=ORANGE, stroke=ORANGE)
    f.txt(338, ly, "里程碑（M1–M5）", size=12.5, color=TEXT2, anchor="start")
    f.txt(520, ly, "13 周 / 5 阶段 / 65 人天（含 2 人天缓冲）· 关键路径 T1.1→T1.2→T3.1→T3.4→T5.1→T5.4",
          size=12.5, color=GRAY, anchor="start")
    return f


# ================================================================ 图 6 请求链路
def fig06():
    f = Fig(1500, 880)
    f.block(40, 50, 220, 70, "客户端", ["浏览器 / 移动端"], title_size=15, body_size=12)
    f.block(320, 50, 240, 70, "Nginx Ingress", ["TLS 终止 · 路由 · 边缘限流"], title_size=15, body_size=12)
    f.arrow([(260, 85), (320, 85)])

    # 中间件链
    f.rect(620, 40, 840, 120, fill=BLUE_SOFT, stroke=BLUE_BORDER, sw=1.6)
    f.txt(640, 66, "中间件链（FastAPI 依赖注入，按序执行）", size=14, color=NAVY, weight="700", anchor="start")
    chips = [("① request_id", "全链路追踪"), ("② JWT 认证", "解析并校验身份"),
             ("③ 限流", "Redis 令牌桶"), ("④ 配额", "日/月额度"),
             ("⑤ Pydantic 校验", "入参结构与范围")]
    for i, (t, s) in enumerate(chips):
        x = 640 + i * 150
        w = 140 if i < 4 else 180
        f.rect(x, 80, w, 60, fill=WHITE, stroke=BLUE_BORDER, sw=1.4, rx=5)
        f.txt(x + w / 2, 104, t, size=12.5, color=NAVY, weight="700")
        f.txt(x + w / 2, 126, s, size=11, color=GRAY)
    f.arrow([(560, 85), (620, 85)])
    f.arrow([(1040, 160), (1040, 210)], sw=2.2)

    # AI 网关
    f.rect(300, 210, 1160, 410, fill="#FFFFFF", stroke=NAVY, sw=2)
    f.txt(320, 244, "AI 网关 · 统一模型出入口", size=16, color=NAVY, weight="700", anchor="start")
    f.txt(320, 268, "配额 / 缓存 / 熔断 / 供应商链 / 结构化校验 / 审计 集中在同一层",
          size=12, color=GRAY, anchor="start")

    f.block(340, 290, 220, 90, "缓存查询", ["Redis · TTL 10 min", "键 = 角色+阶段+入参摘要"], title_size=14, body_size=11.5)
    f.block(620, 290, 220, 90, "熔断器", ["失败率 > 50% 打开", "半开探测恢复"], title_size=14, body_size=11.5)
    f.block(900, 290, 240, 90, "模型链", ["glm-4.7-flash → 4.5 → 4", "单次超时 30 s"], title_size=14, body_size=11.5)
    f.block(1200, 290, 220, 90, "结构化校验", ["Pydantic 校验", "失败重试 1 次"], title_size=14, body_size=11.5)
    f.arrow([(560, 335), (620, 335)])
    f.arrow([(840, 335), (900, 335)])
    f.arrow([(1140, 335), (1200, 335)])

    f.block(900, 470, 520, 90, "降级分支", ["规则底分引擎 → 默认分兜底", "响应标记 degraded=true，并写审计日志"],
            fill=ORANGE_SOFT, stroke=ORANGE_BORDER, title_size=14, body_size=11.5)

    f.arrow([(730, 380), (730, 415), (1000, 415), (1000, 470)], color=ORANGE, sw=1.8)
    f.arrow([(1020, 380), (1020, 442), (1080, 442), (1080, 470)], color=ORANGE, sw=1.8)
    f.arrow([(1310, 380), (1310, 470)], color=ORANGE, sw=1.8)
    f.label(1372, 428, "重试仍失败", size=11.5, color=ORANGE)
    f.arrow([(450, 380), (450, 680)], color=NAVY3, sw=1.8)
    f.label(450, 512, "命中：直接返回", size=12, color=NAVY2)

    # 响应
    f.block(340, 680, 420, 90, "200 OK · 统一响应体", ["score · dimensions · degraded · trace_id"],
            fill=BLUE_FILL, stroke=NAVY, title_size=15, body_size=12)
    f.arrow([(1420, 335), (1448, 335), (1448, 745), (760, 745)], color=NAVY, sw=1.8)
    f.label(1400, 700, "成功", size=11.5, color=NAVY)
    f.arrow([(1160, 560), (1160, 700), (760, 700)], color=ORANGE, sw=1.8)
    f.label(1180, 585, "降级返回", size=11.5, color=ORANGE)

    # 铁律
    f.rect(340, 800, 860, 50, fill=BLUE_FILL, stroke=BLUE_BORDER, sw=1.6)
    f.rect(340, 800, 5, 50, fill=NAVY, stroke=NAVY, sw=0, rx=2)
    f.txt(770, 831, "业务铁律：任何异常分支均返回结构化结果（含 degraded 标记），永不返回 null / 500",
          size=13.5, color=NAVY, weight="700")
    return f


# ================================================================ 图 7 绞杀者迁移
def fig07():
    f = Fig(1500, 660)
    cards = [
        ("状态一 · Node 单跑", "第 1–2 周 · 现状基线", GRAY,
         [("Node", 100), ("Python", 0)], "Node 100%",
         [("错误率", "无统计"), ("AI P95", "2–16 s"), ("降级率", "不可观测")],
         "基线冻结 · golden set 150 条就绪 · M1 达成",
         ["冻结版本与依赖锁", "整理 26 项问题清单"]),
        ("状态二 · 双跑灰度", "第 5–7 周 · 5% → 50%", ORANGE,
         [("Node", 50), ("Python", 50)], "Python 5% → 50%（上限）",
         [("双跑一致率", "≥ 99%"), ("错误率", "≤ 0.1%"), ("降级率", "≤ 3%")],
         "5% 观察 48 h 无 P0 · 一致率 ≥ 99% · 可随时回切",
         ["双写 + 双算 + 比对", "Nginx 权重切量"]),
        ("状态三 · Python 主跑", "第 8–10 周 · 100% 切主", NAVY,
         [("Python", 95), ("Node", 5)], "Python 95% · Node 旁路兜底",
         [("错误率", "≤ 0.1%"), ("AI P95", "≤ 6 s"), ("月度 SLO", "≥ 99.9%")],
         "连续 7 天 SLO 达标 · 零 P0 事故 · Node 无主流量",
         ["PG 为唯一权威", "Node 降为兜底旁路"]),
        ("状态四 · 下线 Node", "第 11–13 周 · 收尾", NAVY,
         [("Python", 100), ("Node", 0)], "Python 100%",
         [("旧链路流量", "0"), ("观察期", "14 天"), ("回滚点", "保留快照")],
         "旧服务 14 天零流量 · 快照归档 · M5 验收通过",
         ["下线 8787 服务", "归档新旧对比报告"]),
    ]
    xs = [30, 405, 780, 1155]
    for (title, weeks, accent, seg, caption, metrics, exitc, actions), x in zip(cards, xs):
        f.rect(x, 70, 315, 465, fill=WHITE, stroke=BLUE_BORDER, sw=1.6)
        f.rect(x, 70, 315, 6, fill=accent, stroke=accent, sw=0, rx=3)
        f.txt(x + 18, 104, title, size=15, color=NAVY, weight="700", anchor="start")
        f.txt(x + 18, 126, weeks, size=11.5, color=GRAY, anchor="start")
        f.line([(x + 16, 140), (x + 299, 140)], color="#E5E7EB", sw=1)

        f.txt(x + 18, 166, "流量分布", size=12, color=GRAY, anchor="start")
        bw = 279
        by = 176
        f.rect(x + 18, by, bw, 24, fill=GRAY_FILL, stroke=GRAY_BORDER, sw=1, rx=4)
        cx = x + 18
        for name, pct in seg:
            if pct <= 0:
                continue
            sw_ = bw * pct / 100
            fill = NAVY if name == "Node" else NAVY3
            f.rect(cx, by + 1, sw_ - 1, 22, fill=fill, stroke=fill, sw=0, rx=3)
            if sw_ > 66:
                f.txt(cx + sw_ / 2, by + 16, f"{name} {pct}%", size=11, color=WHITE, weight="700")
            cx += sw_
        f.txt(x + 18, 220, caption, size=11.5, color=TEXT2, anchor="start")

        f.txt(x + 18, 252, "判定指标", size=12, color=GRAY, anchor="start")
        for i, (k, v) in enumerate(metrics):
            yy = 276 + i * 26
            f.txt(x + 18, yy, k, size=12, color=TEXT2, anchor="start")
            f.txt(x + 297, yy, v, size=12, color=NAVY, weight="700", anchor="end")

        f.rect(x + 18, 352, 279, 66, fill=ORANGE_SOFT, stroke=ORANGE_BORDER, sw=1.4, rx=5)
        from figlib import wrap_text
        lines = wrap_text("退出条件：" + exitc, 249, 11.5)
        yy = 352 + (66 - len(lines) * 16) / 2 + 12
        for ln in lines:
            f.txt(x + 30, yy, ln, size=11.5, color="#8A4B08", anchor="start")
            yy += 16

        f.txt(x + 18, 448, "关键动作", size=12, color=GRAY, anchor="start")
        for i, a in enumerate(actions):
            f.txt(x + 18, 472 + i * 22, "· " + a, size=12, color=TEXT2, anchor="start")

    for i in range(3):
        x1, x2 = xs[i] + 315, xs[i + 1]
        f.arrow([(x1, 330), (x2, 330)], sw=2.2)
        f.txt((x1 + x2) / 2, 318, ["双写", "切主", "下线"][i], size=11.5, color=NAVY, weight="700")

    f.rect(30, 570, 1416, 70, fill=BLUE_FILL, stroke=BLUE_BORDER, sw=1.6)
    f.rect(30, 570, 5, 70, fill=NAVY, stroke=NAVY, sw=0, rx=2)
    f.txt(738, 600, "放量门槛（每一态须同时满足）", size=13.5, color=NAVY, weight="700")
    f.txt(738, 626, "双跑一致率 ≥ 99% · 错误率 ≤ 0.1% · AI P95 ≤ 6 s · 降级率 ≤ 3% · 无 P0 缺陷；任一不达标即回切上一态",
          size=12, color=TEXT2)
    return f


FIGURES = [
    ("fig-01-current-arch", fig01),
    ("fig-02-target-arch", fig02),
    ("fig-03-deploy-topology", fig03),
    ("fig-04-er", fig04),
    ("fig-05-gantt", fig05),
    ("fig-06-request-chain", fig06),
    ("fig-07-migration", fig07),
]


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    want = set()
    for a in args:
        want.add(int(a) if a.isdigit() else int(a.split("-")[1]))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {FIG_DIR}")
    for i, (name, fn) in enumerate(FIGURES, 1):
        if want and i not in want:
            continue
        print(f"[{i}] {name}")
        fig = fn()
        render(fig, FIG_DIR / f"{name}.png")
    print("完成")


if __name__ == "__main__":
    main()

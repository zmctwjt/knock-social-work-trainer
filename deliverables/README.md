# 叩门 · 社工个案面谈 AI 陪练舱 —— 生产化改造交付物说明

本目录是毕业设计成果的完整交付包，主题为"把一个课程作品级的 Node.js 全栈项目改造为可上线的 Python 生产系统"。交付物分为六类：主文档、分章 Markdown、配图、可运行 Python 后端、部署制品、实施计划表。全部数字以 `docs/FACTS.md` 为唯一事实来源，全部结论可回溯到"源码路径:行号"。

## 一 交付物清单

| 编号 | 交付物 | 位置 | 规模 |
| --- | --- | --- | --- |
| D1 | 主文档（Word） | `叩门AI陪练舱_生产化改造与重构方案.docx` | 10 章 + 3 附录，含 7 图 140 表 |
| D2 | 分章 Markdown 源文件 | `docs/00_…` 至 `docs/10_…`、`docs/附录A/B/C` | 14 个文件，约 18 万字符 |
| D3 | 配图源文件（PNG） | `figures/fig-01` … `fig-07` | 1600px 宽，深蓝 #1F3A5F + 橙 #D97706 |
| D4 | 可运行 Python 后端 | `backend/` | 81 个 Python 文件 / 10,904 行，86 个测试用例 |
| D5 | 部署制品 | `deploy/` | 29 个文件（Compose、Nginx、K8s、Prometheus、Grafana、Loki、CI） |
| D6 | 重构实施计划（Excel） | `重构实施计划.xlsx` | WBS 20 项、13 周甘特、风险登记册 R1–R10 |

辅助文件：`docs/OUTLINE.md`（交付物结构与分工）、`docs/STYLE.md`（写作与排版规范）、`docs/FACTS.md`（唯一数字来源）、`docgen/`（配图与文档生成脚本，可一键重出）。

## 二 如何阅读

- 主文档 `叩门AI陪练舱_生产化改造与重构方案.docx`：用 Microsoft Word 或 WPS 打开。目录为 Word 域，若页码未刷新，全选后按 `F9` 选择"只更新页码"或"更新整个目录"。封面与摘要不显示页眉页脚，正文从第 1 章重新编页。
- 分章 Markdown `docs/*.md`：结构、表号、图号与主文档一一对应，适合在编辑器或网页中检索；修改后可用 `docgen/build_docx.py` 重新生成 Word。
- 建议阅读顺序：第 1 章（现状事实）→ 第 2 章（26 项问题，P0 十项）→ 第 3 章（技术选型与总体架构）→ 第 5、6 章（后端与数据库设计）→ 第 4、7、8 章（部署、安全、可观测）→ 第 9、10 章（实施计划与验收）。

## 三 本地运行后端

`backend/` 是一个独立可运行的 FastAPI 工程，默认使用 SQLite 开发模式，无需外部依赖即可跑通页面与接口。

```bash
cd backend
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp env.example .env                                  # 按需填 DATABASE_URL / REDIS_URL / GLM_API_KEY

# 开发模式（SQLite + 建表 + 种子数据）
export APP_ENV=dev AUTO_CREATE_SCHEMA=true
export DATABASE_URL="sqlite+aiosqlite:///./knock_dev.db"
alembic upgrade head
python scripts/seed.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 冒烟
curl -s localhost:8000/healthz
curl -s localhost:8000/api/v1/scenarios | head -c 300
python -m pytest -q                                   # 86 passed
```

生产模式的差异只有配置：`APP_ENV=prod`、`DEBUG=false`、`AUTO_CREATE_SCHEMA=false`、`DATABASE_URL` 指向 MySQL 8.0（`mysql+aiomysql://`）、`REDIS_URL` 指向 Redis 7、`GLM_API_KEY` 填真实密钥。完整环境变量见 `docs/附录B_环境变量与配置清单.md` 与 `backend/env.example`（两者逐项对应，键名与默认值零差异）。

后端详细说明见 `backend/README.md`，接口清单见 `docs/附录A_API接口清单.md`（由 OpenAPI 自动生成，31 条路径），代码规范与目录结构见 `docs/附录C_代码规范与目录结构.md`。

## 四 生产部署

部署方案两阶段：单机 Docker Compose 起步（答辩与院系试点），华为云 CCE 集群收口（正式上线）。所有制品已落盘并通过静态校验。

```bash
cd deploy
cp env.example .env                                   # 填入真实密钥，勿提交
docker compose -f docker-compose.prod.yml up -d       # 11 个服务：api/mysql/redis/nginx/可观测栈
```

- 入口：Nginx 终止 TLS，静态资源由 Nginx/CDN 承担，`/api/v1` 反代到 api:8000；旧 `/api/ai/*` 保留为兼容层。
- 编排：`deploy/k8s/` 12 个清单（Deployment/HPA/PDB/Ingress/NetworkPolicy/Migrate Job 等），`kubectl apply -f deploy/k8s/` 按 `namespace → configmap/secret → migrate-job → deployment` 顺序执行。
- 可观测：Prometheus 抓 `/metrics`（8 条告警规则）、Grafana 10 面板、Loki 日志、Tempo 追踪（采样 10%）、Sentry 异常。
- 备份：MySQL 每日全量到 OBS + binlog 归档，RPO 15 分钟、RTO 1 小时。
- 流水线：`deploy/.github/workflows/ci.yml`，含 lint、单测、Trivy 镜像扫描、构建推送与滚动发布。

部署细节与容量、成本口径见 `docs/04_生产部署方案.md`；安全与合规见第 7 章；可观测与运维见第 8 章。

## 五 重新生成文档与配图

```bash
# 7 张配图（Chrome 无头渲染，需本机 Chrome）
python docgen/render_figures.py --out figures

# Word 主文档（python-docx，读取 docs/*.md + figures/）
python docgen/build_docx.py --docs docs --figures figures --out 叩门AI陪练舱_生产化改造与重构方案.docx

# Excel 实施计划
python docgen/make_xlsx.py --out 重构实施计划.xlsx
```

脚本依赖：`python-docx`、`openpyxl`、`Pillow`，以及无头 Chrome（用于配图）。详细参数见 `docgen/README.md`。

## 六 事实基线

- 现状代码规模：前端 36 文件 12,893 行、Node 后端 3 文件 1,046 行、Supabase 迁移 472 行、Edge Function 280 行、工具脚本 753 行，合计 16,331 行。
- 业务资产（已逐项核实）：12 位服务对象、118 个台词节点（354 句）、19 张技巧卡、11 条伦理守则 + 1 条边界声明、162 条判定词表、8 步判定、六维权重 25/20/15/20/10/10、综合分 = 规则底分 × 0.4 + AI 评分 × 0.6、69 项引擎断言。
- 交付后端实测：81 个 Python 文件 / 10,904 行；`pytest -q` 为 86 passed；`alembic upgrade head` 与 `alembic check` 无漂移；uvicorn 冒烟 `/healthz`、`/readyz`、`/metrics`、`/api/v1/scenarios`、`/api/health` 均为 200。
- 数据模型：目标库 11 张表（10 张业务表 + 1 张令牌撤销表）、18 个普通索引、9 个唯一约束。
- 改造中修正的 6 处原始声明偏差（视图 2→5、词表 165→162、阻抗形态 10→6、默认 AI 模式"混合"→`ai`、`user_settings` 缺 `ai_mode` 列、`scenarios.nodeCount` 11 个角色与真实树不符）已写入第 1、2 章与 FACTS.md。

## 七 未实测项与原因

以下项目受本机环境限制未做端到端实测，已在文档中标注，需在目标环境补齐：

- [x] MySQL 8.0 + aiomysql 真实实例：迁移（`alembic upgrade head` / `alembic check`）、12 场景 19 知识卡种子、登录-建会话-发言-分段评分-结案-统计端到端已在 127.0.0.1:3307 实测通过。
- [ ] 真实 Redis 7：内存实现与接口一致性有测试，RedisStore 未起服务实测。
- [ ] 真实智谱 GLM 调用：全程 FakeProvider，`GLM_API_KEY` 为空，未消耗真实额度。
- [ ] 100 RPS 并发压测：限流、熔断、配额有单测，SLO 数字来自设计预算。
- [ ] Docker 镜像构建与容器内运行：本机 Docker daemon 未运行，`docker compose config` 静态校验通过。
- [ ] `nginx -t`、`kubectl --dry-run=server`：无 Nginx 与集群环境，已用 YAML/schema 静态校验替代（22 个 YAML/JSON 解析通过、19 个 k8s 对象离线 schema 通过）。
- [ ] ruff / mypy 全量检查：规则已配置，本次未跑全量静态检查（单测全绿）。

目标环境最小验证序列（依次执行即可把这些从"未实测"转为"已验证"）：

```bash
docker compose up -d mysql redis                    # 或使用已有实例
export DATABASE_URL='mysql+aiomysql://knock:knock@localhost:3306/knock?charset=utf8mb4'
export REDIS_URL=redis://localhost:6379/0 GLM_API_KEY=<真实 key>
cd backend && alembic upgrade head && alembic check
python -m uvicorn app.main:app --port 8000 &
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/healthz
curl -s localhost:8000/api/v1/scenarios | head -c 200
python -m pytest -q
```

## 八 目录结构

```
deliverables/
├─ 叩门AI陪练舱_生产化改造与重构方案.docx   主文档（D1）
├─ 重构实施计划.xlsx                          WBS / 甘特 / 风险（D6）
├─ README.md                                 本说明
├─ docs/                                     分章源文件 + FACTS/OUTLINE/STYLE（D2）
├─ figures/                                  7 张配图（D3）
├─ backend/                                  FastAPI 后端、测试、Dockerfile（D4）
├─ deploy/                                   Compose / Nginx / K8s / 监控 / CI（D5）
└─ docgen/                                   配图与文档生成脚本
```

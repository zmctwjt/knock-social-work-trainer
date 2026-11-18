# 交付物总纲（Lead 锁定，勿擅自改动）

## 1 最终交付物

| 编号 | 路径 | 说明 |
|---|---|---|
| D1 | `deliverables/叩门AI陪练舱_生产化改造与重构方案.docx` | 主文档，A4，含封面/摘要/目录/10章/3附录/图 |
| D2 | `deliverables/docs/*.md` | 章节 Markdown 源（docx 由源生成，改内容只改 md） |
| D3 | `deliverables/figures/*.png` | 架构图/拓扑图/ER图/甘特图（由 docgen 渲染） |
| D4 | `deliverables/backend/**` | 可运行的 Python FastAPI 生产级后端骨架（含测试、Docker、迁移） |
| D5 | `deliverables/deploy/**` | 部署与运维制品（compose/k8s/nginx/prometheus/CI） |
| D6 | `deliverables/重构实施计划.xlsx` | WBS / 甘特 / 风险登记册 三张表 |

## 2 章节与负责人

| 章 | 文件 | 负责人 | 内容要求 |
|---|---|---|---|
| 封面/摘要/目录 | `docs/00_封面与摘要.md` | Lead | 封面字段、中文摘要 600-800 字、关键词、英文摘要 |
| 第1章 项目现状分析 | `docs/01_现状分析.md` | analyst | 见下 1.1-1.9 |
| 第2章 现状问题诊断 | `docs/02_问题诊断.md` | analyst | 26 项问题清单，A-F 六组，P0/P1/P2 分级 |
| 第3章 技术选型与总体架构 | `docs/03_技术选型与总体架构.md` | Lead | 选型对比+ADR+目标架构 |
| 第4章 生产部署方案 | `docs/04_生产部署方案.md` | devops | 环境/容器/编排/发布/备份/容量/上线手册 |
| 第5章 Python后端详细设计 | `docs/05_Python后端详细设计.md` | backend | 分层/中间件/认证/AI网关/领域下沉/兼容 |
| 第6章 数据库设计与迁移 | `docs/06_数据库设计与迁移.md` | backend | ER/表结构/索引/权限/迁移/治理 |
| 第7章 安全与合规方案 | `docs/07_安全与合规方案.md` | devops | STRIDE/AI风险/社工伦理/个保法/审计 |
| 第8章 可观测性与运维保障 | `docs/08_可观测性与运维保障.md` | devops | SLO/指标/日志/追踪/告警/预案 |
| 第9章 重构实施计划 | `docs/09_重构实施计划.md` | Lead | 绞杀者策略/5阶段13周/WBS/风险/测试/回滚 |
| 第10章 验收标准与上线检查单 | `docs/10_验收标准与上线检查单.md` | Lead | 功能/非功能验收 + Go-NoGo 清单 + 演进路线 |
| 附录A API 接口清单 | `docs/附录A_API接口清单.md` | backend | 由 OpenAPI 生成，逐接口：方法/路径/鉴权/入参/出参/错误码 |
| 附录B 环境变量与配置清单 | `docs/附录B_环境变量与配置清单.md` | devops | 分组表：变量/含义/示例/是否必填/密级 |
| 附录C 代码规范与目录结构 | `docs/附录C_代码规范与目录结构.md` | backend | 目录树 + ruff/mypy/pytest + 命名与提交规范 |

## 3 锁定技术栈（所有章节不得与之冲突）

**后端**：Python 3.12 · FastAPI · Uvicorn/Gunicorn · Pydantic v2 · pydantic-settings · SQLAlchemy 2.0 async + asyncpg + Alembic · PostgreSQL 16 · Redis 7 · httpx · Argon2id · PyJWT · ARQ（异步任务）· structlog · prometheus-client · OpenTelemetry · ruff + mypy + pytest

**前端**：保留 React 18.3 + TypeScript 5.6 + Vite 5.4 + Tailwind 3.4（不重写；仅改造 API 调用层与鉴权，静态产物上 CDN/Nginx）

**AI**：智谱 GLM-4.7-Flash 为主模型，`glm-4.5-flash → glm-4-flash` 降级链；后端统一 AI 网关，`LLMProvider` 协议可切换 OpenAI-compatible 供应商；结构化输出用 Pydantic 校验；保留"规则主干 + AI 长尾""危机永不调模型""AI 失败静默降级"三条业务铁律

**部署运维**：Docker 多阶段构建 · Docker Compose（开发/单机）· Kubernetes（华为云 CCE 生产，兼容 ACK）· Nginx Ingress + cert-manager · Prometheus + Grafana + Loki + Tempo · Sentry · GitHub Actions · Trivy · PgBouncer · 对象存储（OBS/MinIO）

## 4 锁定架构决策（ADR 摘要，展开由 Lead 写第3章）

- ADR-01 后端用 FastAPI 而非 Django/Flask：异步 IO 密集（LLM 调用）+ 原生 OpenAPI + Pydantic 校验
- ADR-02 业务逻辑下沉服务端：成绩可信、危机拦截不可绕过、规则可复算
- ADR-03 保留 React 前端，不做 SSR：改造成本最低，静态化利于 CDN 与灰度
- ADR-04 PostgreSQL 单库起步 + 读写分离演进：结构化成绩/统计需求强，JSONB 兼容内容资产
- ADR-05 AI 网关统一出入口：配额/缓存/熔断/审计/供应商切换集中一处
- ADR-06 认证采用 JWT + RBAC：学生/教师/管理员三角色，保留游客体验模式
- ADR-07 绞杀者模式迁移：新旧 `/api/ai/*` 双跑对比，按链路灰度切换
- ADR-08 单机 Compose 起步、K8s 收口：毕业设计可交付，同时具备生产扩展路径

## 5 关键一致性要求

1. 所有数字（行数、表数、接口数、时延、成本）必须来自 `docs/FACTS.md`，需要新增数字时先追加到 FACTS.md 再引用。
2. 接口路径统一 `/api/v1/...`；旧接口 `/api/ai/{intent|persona|score|debrief}` 作为兼容层保留并在第5章说明。
3. 术语统一：学生 / 服务对象 / 督导（AI 陪练中的角色）/ 教师 / 训练记录 / 六维评分 / 三阶段。
4. 每个问题、每条方案都要能追溯到证据（`文件:行`）或明确标注为"建议/设计决策"。
5. 图表编号全局连续：图 1-1、图 3-1…；表 2-1、表 4-1…（按章编号，不跨章连续）。
6. 不写"TODO/待补充/示例数据"，所有表填真实设计值。

## 6 协作规则

- 只写自己负责的文件（见第2节），不修改他人章节；需要联动时用 `send_message` 通知 Lead。
- 每章写完后 `send_message` 给 lead：文件路径 + 字数 + 关键结论 3-5 条 + 与其他章的依赖点。
- 图片引用：`![图 N-M 名称](figures/fig-XX-名称.png)`，图片文件由 docsmith 生成，命名见 `docs/STYLE.md`。

# 叩门 · 社工个案面谈 AI 陪练舱

[![CI](https://github.com/zmctwjt/knock-social-work-trainer/actions/workflows/ci.yml/badge.svg)](https://github.com/zmctwjt/knock-social-work-trainer/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![License](https://img.shields.io/badge/license-学习用途-lightgrey)](#十二-许可)


面向社会工作专业实训的**多角色对话陪练与教学管理系统**。依据民政部行业标准
《社会工作方法 个案工作》（MZ/T 094-2017）构建训练流程与评分依据。

学生与 AI 扮演的服务对象进行面谈训练，系统按六个维度实时评分并给出条款依据；
教师查看名下学员的班级看板与训练画像；管理员管理账号、内容与平台运行状态。

---

## 一 功能概览

### 训练端（学生）

| 功能 | 说明 |
| --- | --- |
| 角色选择 | 12 类服务对象，三档难度（简单实习 / 标准实训 / 挑战督导） |
| 面谈训练 | 逐句输入、快捷话术、三阶段推进（建立关系 / 问题探索 / 评估介入） |
| 实时评分 | 六维评分 + 逐句点评，每条判定可溯源到标准条款 |
| 阶段结算 | 每阶段汇总，展示得分构成与命中规则 |
| 复盘报告 | 三段式复盘，指出薄弱项与改进方向 |
| 成长中心 | 六维雷达、成长曲线、训练热力图、**老师点评** |
| 知识库 | 19 张技巧卡 + 12 条伦理守则，支持**按案例 + 关键词 + 六维**三重检索 |
| 危机处置 | 识别高风险表述并中止对话，提示转介与上报 |

### 教师端

| 功能 | 说明 |
| --- | --- |
| 班级总览 | 学员数、训练量、班级均分、最薄弱维度；按用户名绑定学员 |
| 学员画像 | 六维雷达、14 天进步曲线、案例分布、最近训练记录 |
| 训练趋势 | 班级均分趋势（双轴）、六维均值、案例练习分布 |
| **教师点评** | 对学员单次训练写点评（表现良好/需关注/需干预），学员在成长中心可见 |
| **成绩导出** | 一键导出班级成绩 CSV（含六维明细），Excel 直接打开不乱码 |
| 内容查阅 | 检索技巧卡与伦理守则作为教学参考 |

### 管理端

| 功能 | 说明 |
| --- | --- |
| 运行概览 | 账号/会话/记录统计、AI 服务状态、调用成功率与延迟 |
| 账号管理 | 教务导入建号（三角色）、搜索筛选、批量启用停用 |
| 平台趋势 | 30 天均分趋势、**平台训练热力图**、六维均值、角色分布、案例热度 |
| 内容维护 | 案例与技巧卡的新增、编辑、下架、删除 |
| 判定词表 | 九个词表分组维护，危机组受保护（禁止禁用） |
| 台词节点 | 按情绪档与角色维护服务对象台词 |
| **操作审计** | 记录账号启停、内容增删等管理动作，摘要对口令打码 |

---

## 二 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | React 18.3 · TypeScript 5.6 · Vite 5.4 · Apache ECharts 6.1 |
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Alembic · Pydantic v2 |
| 数据库 | MySQL 8.0（aiomysql 驱动） |
| 鉴权 | PyJWT（access/refresh）+ Argon2id 口令哈希 + RBAC 四角色 |
| AI | httpx 自建网关对接智谱 GLM-4.7-Flash（含降级链） |
| 观测 | structlog · Prometheus · OpenTelemetry（可选） |
| 测试 | pytest（162 用例）+ 10 个端到端审查脚本 |

---

## 三 文档

| 文档 | 内容 |
| --- | --- |
| [使用说明书](docs/使用说明书.md) | 面向使用者的完整操作手册：环境要求、安装启动、三类角色操作流程、常见问题排查 |
| [部署验证状态](docs/部署验证状态.md) | 诚实记录哪些已验证、哪些只是设计制品、哪些明确未做 |
| [迭代记录与自审](docs/迭代记录.md) | 按任务书迭代的 8 轮过程，每轮含自审结论与修掉的真实缺陷 |
| [设计文档](docs/design/) | 现状分析、技术选型、数据库设计、安全方案、可观测性、验收标准等 17 篇 |
| `/docs`（运行时） | 接口文档（开发环境自动挂载，生产环境默认关闭） |

## 四 快速开始

### 前置要求

- Python **3.12**
- Node.js **18.17+**（推荐 20 LTS）
- MySQL **8.0**（本地实例或 Docker）

### 一键启动（Windows）

双击根目录 `start.bat`。脚本按顺序检查并拉起：MySQL → 数据库迁移 → 前端构建 → FastAPI，
已运行的组件自动跳过（幂等）。

### 手动启动

```bash
# 1. 后端依赖
cd deliverables/backend
python -m venv .venv && .venv\Scripts\activate     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env                                  # 按需修改 DATABASE_URL

# 2. 数据库
mysql -u root -p -e "CREATE DATABASE knock CHARACTER SET utf8mb4"
alembic upgrade head
python scripts/seed.py                               # 12 个案例 + 19 张技巧卡

# 3. 启动后端
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. 前端（另开终端）
cd src
npm ci
npm run build        # 产物由后端托管，单端口 8000 即可访问
# 或开发模式：npm run dev（5173，热更新）
```

打开 **http://localhost:8000**。

---

## 五 演示账号

账号不开放自助注册（对应"账号由教务统一创建"的教学管理设定）。
首次启动后运行 `python ../../work/seed_demo_accounts.py` 生成演示账号：

| 角色 | 用户名 | 密码 | 进入 |
| --- | --- | --- | --- |
| 学生 | `student01` | `Student@12345` | 训练首页 |
| 教师 | `teacher01` | `Teacher@12345` | 班级看板 |
| 管理员 | `admin01` | `Admin@12345` | 管理后台 |
| 访客 | 登录页一键进入 | 无 | 只读浏览 |

登录页内置三个演示账号的一键填入按钮。

---

## 六 项目结构

```text
.
├─ frontend/                     前端（React + TypeScript + ECharts）
│  ├─ pages/                      页面：训练、结算、复盘、成长、教师工作台、管理后台
│  ├─ components/charts.tsx       ECharts 图表组件（趋势/维度/雷达/饼图/热度）
│  ├─ lib/authClient.ts           账号与鉴权（令牌、角色、角色化导航）
│  ├─ lib/aiClient.ts             AI 链路客户端 + 降级
│  ├─ store/store.tsx             全局状态：账号、训练会话、记录
│  └─ services/                   规则引擎、评分、对话、危机分级
├─ deliverables/backend/          后端（FastAPI）
│  ├─ app/api/v1/                 业务接口：auth/scenarios/sessions/stats/ai/roles
│  ├─ app/api/legacy.py           旧接口兼容层（/api/ai/*）
│  ├─ app/domain/                 领域层：规则词表、六维评分、危机判定、ORM 模型
│  ├─ app/services/               AI 网关、会话、统计、分析、账号、审计
│  ├─ app/core/                   配置、鉴权、日志、指标、中间件、限流
│  ├─ alembic/                    数据库迁移（7 个版本）
│  └─ tests/                      pytest 用例
├─ deliverables/deploy/           部署制品（Compose / K8s / Nginx / Prometheus / CI）
├─ work/
│  ├─ run_all.py                  一键启动器
│  ├─ audit_*.py                  端到端审查脚本（权限/角色/接口/界面）
│  └─ seed_*.py                   演示数据生成
└─ docs/
   ├─ 使用说明书.md                产品使用说明书（任务书预期成果）
   └─ design/                     设计文档（现状分析/选型/后端/数据库/安全/运维/接口清单）
```

---

## 七 架构要点

### 规则主干 + AI 长尾

确定性判定（171 条词表、8 步意图判定、六维权重、三级风险）全部是纯函数，
命中即免调模型；只有长尾语义交给 GLM。**每条 AI 链路都有独立降级分支**——
断网、超时、解析失败、配额耗尽都回落规则结果，接口永不返回 null。

### 危机内容零模型调用

命中危机表述由本地硬规则短路，不构造任何提示词、不进入模型调用。
单元测试以 mock 断言 `provider.calls == []` 来证伪"漏调模型"。

### 键盘可达与语义正确

工作台与知识库的标签组按 WAI-ARIA tabs 模式实现：`role=tablist/tab/tabpanel`
三者通过 `id ↔ aria-controls ↔ aria-labelledby` 关联，非选中标签
`tabIndex=-1`（否则键盘用户要被逐个标签卡住），支持 ←/→/Home/End。
用 CDP 派发真实按键事件验证，不是 JS 合成事件。

顶栏从 `role=tablist` 改为普通 `<nav>` + `aria-current="page"`：
它是页面间跳转，不是页内标签，用 tab 语义会让读屏念成"标签 3/9"。

### 前端不白屏

路由内容外挂 `ErrorBoundary`：任一页面在渲染期抛异常时显示可读错误页并给出
「重试 / 回首页」两个出口，顶栏保持可用（只包路由内容而非整棵树）。
已验证：用临时崩溃路由触发后，兜底页正常显示、顶栏仍在、恢复按钮有效；
验证后移除探针路由，不留在产物里。

### 成绩可复算

评分与判定逻辑全部在服务端（1,090 行 TypeScript 规则移植为 Python 领域层），
前端篡改无效。会话与记录带 `owner_id`，学员带 `teacher_id` 归属，
所有按 ID 读取的入口先查主键再比归属，越权返回 40301 而非 40401。

### 内容可维护而安全不可削弱

基线词表与台词固化在代码里（保证库故障时判定与对话仍可用），
数据库只存增量与禁用记录，启动时加载为内存快照，判定路径零 IO。
危机与无望感两组在接口层禁止禁用（40301）。

### 生产环境强校验

默认 JWT 密钥、`DEBUG`、通配 `ALLOWED_HOSTS`/`CORS_ORIGINS`、SQLite、
缺 Redis、关闭限流、自动建表——这八项在 `APP_ENV=prod` 时任一命中即
抛 `StartupConfigError` 让进程拒绝启动，不做降级、不写警告了事。

---

## 八 测试与审查

Linux/macOS 下用 Makefile 统一入口：

```bash
make help          # 列出全部命令
make install       # 安装前后端依赖
make dev           # 同时起后端(8000)与前端(5173)
make test          # 后端单元测试
make build         # 前端类型检查 + 生产构建
make audit         # 跑全部端到端审查（需服务已启动）
make migrate       # 数据库迁移
```

Windows 下直接跑脚本（本机未装 make 也能用）：

```bash
# 单元测试：143 passed
cd deliverables/backend && python -m pytest

# 端到端审查，逐个跑（需服务已启动）
python work/audit_permissions.py     # 四角色 × 全接口权限矩阵
python work/audit_roles_ui.py        # 三角色登录与页面隔离
python work/audit_role_landing.py    # 角色化落地页与导航裁剪
python work/audit_extended_api.py    # 扩展接口权限与健壮性
python work/audit_workbench_ui.py    # 教师/管理页全部标签页渲染
python work/audit_confirm.py         # 危险操作二次确认
python work/audit_comments.py        # 教师点评权限与流程
python work/audit_comment_ui.py      # 点评端到端闭环（教师发布→学生可见）
python work/audit_knowledge.py       # 知识库按案例 + 关键词检索
python work/audit_training_flow.py   # 核心训练流程（输入→评分→结算→成长→危机处置）
python work/audit_a11y.py            # 标签页 ARIA 关联与键盘导航
python work/audit_mobile.py          # 移动端 390px 无横向溢出
python work/audit_confirm.py         # 危险操作二次确认
```

CI（`.github/workflows/ci.yml`）在每次推送时运行四个 job：

| job | 内容 |
| --- | --- |
| backend | pytest（SQLite）+ 在真实 MySQL 8.0 上执行迁移与 `alembic check` |
| frontend | tsc 类型检查 + vite 构建 + 校验图表库未进首屏 |
| **e2e** | 真实 MySQL + 无头 Chrome，跑 12 个端到端审查脚本 |
| security | 密钥误提交扫描 + pip-audit 依赖漏洞 |

**测试分布**（18 个模块 / 161 个测试函数，pytest 收集 162 项——含 1 个参数化展开）：

| 领域 | 模块 | 用例 | 覆盖内容 |
| --- | --- | --- | --- |
| 领域规则 | 2 | 23 | 六维评分权重、危机分级、词表判定 |
| 认证与安全 | 3 | 22 | 登录/刷新/令牌撤销、限流、安全响应头 |
| 训练流程 | 2 | 17 | 会话生命周期、逐句提交、阶段结算、幂等 |
| 多角色权限 | 1 | 12 | 教师归属隔离、管理端接口越权 |
| 内容维护 | 3 | 19 | 案例/技巧卡/词表/台词增删改 |
| 分页与统计 | 3 | 17 | 游标分页、个人统计、平台热力图 |
| 教师点评 | 1 | 13 | 点评权限、未读标记、CSV 导出 |
| AI 与探针 | 2 | 16 | 降级链、配额、缓存、健康检查 |
| 工程健壮性 | 1 | 22 | 生产配置强校验、文档暴露、pid 泄露 |

**合计**：18 个模块 / 161 个测试函数 → `pytest` 报告 `162 passed`。

> 注：**未统计行覆盖率**。本机 Python 环境由 uv 管理、不含 pip，
> 按「不额外安装软件」的约束未安装覆盖率工具。CI 环境已声明
> `pytest-cov` 依赖，需要时可执行 `pytest --cov=app` 获取。

端到端审查脚本可通过环境变量适配不同平台：
`UI_BASE`（服务地址）、`CHROME_PATH`（浏览器路径）、`CDP_PORT`、`QA_DIR`（截图目录）。

---

## 九 主要接口

| 分组 | 路径 |
| --- | --- |
| 探针 | `/healthz` `/readyz` `/metrics` |
| 认证 | `/api/v1/auth/{login,refresh,guest,logout,me}` |
| 案例 | `/api/v1/scenarios` `/api/v1/knowledge/cards?keyword=` |
| 训练 | `/api/v1/sessions`（+ `turns` / `stages/{n}/score` / `finish` / `debrief`） |
| 统计 | `/api/v1/stats/{me,heatmap}` |
| AI | `/api/v1/ai/{intent,persona,score,debrief}` |
| 教师 | `/api/v1/teacher/{learners,stats,trend,learners/{id}/detail}` |
| 管理 | `/api/v1/admin/{overview,accounts,trend,ai-logs,scenarios,cards,rule-words,script-lines}` |
| 点评 | `/api/v1/teacher/comments`（写/删）、`/api/v1/comments/{mine,unread}` |
| 导出 | `/api/v1/teacher/export.csv` |
| 审计 | `/api/v1/admin/audit-logs` |
| 热力图 | `/api/v1/stats/heatmap`（个人）、`/api/v1/admin/heatmap`（平台） |

完整清单见 `docs/design/附录A_API接口清单.md`，或在服务运行时访问 `/docs`。

---

## 十 配置

全部通过环境变量配置，清单见 `deliverables/backend/env.example`。
最常改的三个：

```ini
DATABASE_URL=mysql+aiomysql://knock:knock@127.0.0.1:3306/knock?charset=utf8mb4
GLM_API_KEY=你的智谱密钥          # 留空则全程规则模式，功能完整
JWT_SECRET=至少32字符的随机串      # 生产环境必须替换
```

---

## 十一 已知边界

- AI 能力依赖外部模型服务；未配置密钥时走规则模式，训练流程完整但台词取自预置库。
- 作业分发、班级实体属二期（当前用 `teacher_id` 做简易归属）。
- 移动端做了基础适配（<=720px 断点，390px 下无横向溢出），但交互仍以桌面为主。
- 训练记录分页上限 100 条/页；账号列表 200 条/页。

**未验证项**（详见 [部署验证状态](docs/部署验证状态.md)）：
- AI 供应商真实调用未验证（开发全程未配置密钥，走规则模式）
- Docker Compose / K8s / Nginx 制品齐备但未在真实环境启动
- 未做并发压测；性能数字来自设计估算
- 移动端仅 Chrome 模拟，未在真机与多浏览器验证

---

## 十二 许可

本项目为毕业设计成果，仅供学习与教学参考。
训练内容依据 MZ/T 094-2017 编写，标准文本版权归民政部所有。

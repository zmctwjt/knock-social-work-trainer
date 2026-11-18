# 叩门·社工个案面谈 AI 陪练舱 —— 后端服务

Python 3.12 + FastAPI 生产级后端，承接原 Node.js 零依赖服务的全部业务：训练会话、
六维评分、危机硬拦截、AI 四链路（意图/扮演/评分/复盘）、统计看板与旧接口兼容。
技术选型与设计依据见 `deliverables/docs/05_Python后端详细设计.md`，
数据模型见 `deliverables/docs/06_数据库设计与迁移.md`。

## 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.12 | 与镜像 `python:3.12-slim` 一致 |
| MySQL | 8.0 | 生产库（驱动 aiomysql）；开发可退化为 SQLite |
| Redis | 7 | 限流、AI 缓存、每日配额；留空则退化为进程内实现 |
| gunicorn | 23 | 仅 Linux 镜像使用；Windows 本机用 uvicorn |

## 2. 八分钟启动（开发模式，SQLite + 内存缓存）

```bash
cd deliverables/backend

# ① 建虚拟环境并装依赖（Windows 用 py -3.12）
python -m venv .venv
. .venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
python -m pip install --no-cache-dir -r requirements.txt

# ② 配置环境变量：默认值即可跑通，不需要 API key
cp env.example .env

# ③ 建表（SQLite 文件会自动创建）
python -m alembic upgrade head

# ④ 写入 12 个案例与 19 张技巧卡
python scripts/seed.py

# ⑤ 启动
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# ⑥ 另一个终端验证
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/api/v1/scenarios | head -c 200
```

没有 `GLM_API_KEY` 时 AI 链路自动降级为规则模式：接口仍然返回 200，
`meta.used_ai=false`、`degrade_reason=no_key`，页面拿到规则兜底结果，不会报错。

## 3. 常用命令

```bash
python -m pytest -q                 # 全部用例（86 条，不依赖 PG/Redis）
python scripts/smoke.py             # 端到端冒烟（10 项检查）
python -m ruff check app tests scripts
python -m mypy app
python scripts/gen_api_doc.py       # 重新生成附录 A
```

## 4. Docker

```bash
# 单容器
docker build -t knock-backend:local .
docker run --rm -p 8000:8000 -e DATABASE_URL=sqlite+aiosqlite:///./knock_dev.db knock-backend:local

# 本地三件套（api + mysql + redis）
docker compose up --build
```

镜像约定（与 `deploy/` 下的编排和探针一致）：

- 运行阶段名 `runtime`，UID 10001 非 root，监听 8000；
- `HEALTHCHECK` 请求 `/healthz`；
- 启动命令 `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000 --timeout 90 --graceful-timeout 30`。

## 5. 端点总览

| 类别 | 路径 |
| --- | --- |
| 探针 | `GET /healthz`、`GET /readyz`、`GET /metrics` |
| 认证 | `/api/v1/auth/{login,refresh,guest,me,logout}` |
| 案例 | `GET /api/v1/scenarios`、`GET /api/v1/scenarios/{id}`、`GET /api/v1/knowledge/cards` |
| 会话 | `POST/GET /api/v1/sessions`、`GET /api/v1/sessions/{id}`、`POST .../turns`、`POST .../stages/{n}/score`、`POST .../finish`、`POST .../debrief` |
| 统计 | `GET /api/v1/stats/me`、`GET /api/v1/stats/heatmap` |
| AI | `POST /api/v1/ai/{intent,persona,score,debrief}` |
| 旧版兼容 | `/api/health`、`/api/usage`、`/api/selftest`、`/api/ai/*`（带 Deprecation 头） |

完整字段与响应码见 `deliverables/docs/附录A_API接口清单.md`（由 OpenAPI 生成）。

## 6. 配置要点

- 全部配置走环境变量，无前缀、大小写不敏感，清单见 `env.example`；
- `DATABASE_URL` 缺省为 `sqlite+aiosqlite:///./knock_dev.db`，生产/本机 MySQL 用 `mysql+aiomysql://knock:knock@127.0.0.1:3306/knock?charset=utf8mb4`；
- `REDIS_URL` 留空时用进程内实现，**多进程/多副本部署必须配 Redis**，否则限流与配额不跨进程；
- `JWT_SECRET` 生产必须替换；`GLM_API_KEY` 缺失时进入规则模式；
- `AUTO_CREATE_SCHEMA` 仅开发方便，生产用 `alembic upgrade head`。

## 7. 目录结构

```
backend/
  app/{api,core,domain,infra,prompts,services,main.py}   # 分层代码
  alembic/versions/0001_initial_schema.py                # 初始迁移
  tests/                                                 # 86 条用例
  scripts/{seed.py,smoke.py,gen_api_doc.py}              # 运维与文档脚本
  Dockerfile  docker-compose.yml  requirements.txt  env.example  Makefile
```

## 8. 已知边界（二期）

- 账号仅有登录/刷新/游客，自助注册、教师端作业批改、SMTP 通知属二期；
- OTel 仅做初始化开关，未接入真实 collector 的端到端验证；
- 本机 Windows 无法运行 gunicorn，镜像内的 gunicorn 启动未在本机实测。

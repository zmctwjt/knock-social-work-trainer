# deploy/ —— 叩门·AI 陪练舱 部署制品

本目录是第 4 章（生产部署方案）的可执行落地物，覆盖「单机 Docker Compose 全栈」与「华为云 CCE / K8s 集群」两个阶段。
所有 YAML/JSON 均可被解析器直接读取，不含占位型语法错误；示例密钥一律为 `CHANGE_ME` 占位符。

## 1. 目录结构

| 路径 | 作用 |
| --- | --- |
| `docker-compose.prod.yml` | 阶段一全栈编排：api、mysql、redis、nginx、prometheus、grafana、loki 与四个 exporter |
| `env.example` | Compose 使用的 `.env` 模板，键名与 `backend/app/core/config.py` 对齐 |
| `nginx/nginx.conf` | 主配置：日志格式、TLS 策略、gzip、限流 zone、上传体大小 |
| `nginx/conf.d/app.conf` | 虚拟主机：`api.` / `www.` / `admin.` 三个域名与安全响应头 |
| `nginx/certs/` | 证书目录（仅放 README 与 .gitignore，真实证书不入库） |
| `mysql/init/` | 初始化监控只读账号（exporter）与实例时区 |
| `static/` | 前端构建产物挂载点 |
| `prometheus/` | 抓取配置、告警规则、blackbox 探针模块 |
| `grafana/` | 数据源与仪表盘自动装载 |
| `loki/` | 单机日志存储配置 |
| `k8s/` | 12 个集群清单：命名空间与配额、配置、Secret、工作负载、网关、弹性、可用性、网络策略 |
| `.github/workflows/ci.yml` | 流水线：lint → test → build/push → trivy → 审批部署 |

## 2. 前置条件

- Docker Engine 24+ 与 Compose v2（`docker compose version` 可见 v2.x）。
- 域名解析：`api.` `www.` `admin.` 三个 A 记录指向入口 IP；生产用 cert-manager + Let's Encrypt，本地自签见 `nginx/certs/README.md`。
- 镜像：`backend/Dockerfile` 由后端组提供，多阶段构建、`runtime` 阶段为最终镜像、容器内监听 8000。
- 数据库：MySQL 8.0（`mysql:8.0` 镜像，字符集 utf8mb4、排序规则 utf8mb4_general_ci），驱动 `mysql+aiomysql`，容器内端口 3306。
- 集群阶段：MySQL 实例与 Redis 实例位于 `knock-data` 命名空间（或云托管），地址由 Secret 的 `DATABASE_URL` / `REDIS_URL` 指定；本目录不含数据库工作负载清单，仅含连接与网络策略。
- 机密：`.env` 不提交入库；生产密钥由 KMS/CSMS 托管并注入。

## 3. 本地起全栈（阶段一）

```bash
cd deploy
cp env.example .env                 # 填入数据库口令、GLM_API_KEY、JWT_SECRET
# 机密占位共 6 类：__CHANGE_ME__（DB/Redis/Grafana 通用口令）
#              __CHANGE_ME_ROOT__（MySQL root）、__CHANGE_ME_EXPORTER__（监控只读账号）
sed -i 's/__CHANGE_ME__/实际口令/g' .env

# 自签证书（仅本地/预发）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem -out nginx/certs/fullchain.pem \
  -subj "/CN=api.knock.example.com"

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

浏览器访问 `https://localhost/`（自签会告警，属预期），`admin.` / `www.` 通过 `/etc/hosts` 指向 127.0.0.1。

## 4. 验证命令

```bash
# 存活探针：恒 200，仅证明进程在
curl -sk https://localhost/healthz -o /dev/null -w "%{http_code}\n"

# 就绪探针：DB 连通 + AI 密钥就绪才 200，否则 503
curl -sk https://localhost/readyz

# 指标端点：容器内可直接取，外部被 Nginx 按网段限制
docker compose -f docker-compose.prod.yml exec api \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').status)"

# 数据库连通性（MySQL 8.0，容器内）
docker compose -f docker-compose.prod.yml exec mysql \
  mysqladmin ping -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD" --silent

# 业务链路（需有效 token；未登录应返回 401 而非 500）
curl -sk -X POST https://localhost/api/v1/auth/login \
  -H 'content-type: application/json' -d '{"username":"demo","password":"demo12345"}'

# 容器资源与健康
docker compose -f docker-compose.prod.yml ps --format 'table {{.Name}}\t{{.Status}}'
docker stats --no-stream
```

Prometheus `http://127.0.0.1:9090`（`/alerts` 看告警状态，`/targets` 看抓取）、Grafana `http://127.0.0.1:3000`（`admin` 账号，首登改密）。

## 5. K8s 部署（阶段二）

```bash
# 0) 上下文与镜像仓库登录
kubectl config use-context prod-cce
kubectl create secret docker-registry harbor-cred \
  --docker-server=swr.cn-north-4.myhuaweicloud.com \
  --docker-username=<AK> --docker-password=<SK> -n knock-prod

# 1) 命名空间、配额、配置与机密（secret 由 ESO/KMS 同步，勿手动入库）
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/service.yaml -f k8s/pdb.yaml -f k8s/hpa.yaml

# 2) 数据库迁移（必须先于滚动，且迁移脚本向前兼容）
kubectl apply -f k8s/migrate-job.yaml
kubectl -n knock-prod wait --for=condition=complete job/knock-db-migrate --timeout=300s

# 3) 工作负载与入口
kubectl apply -f k8s/web.yaml
kubectl apply -f k8s/deployment.yaml
kubectl -n knock-prod rollout status deployment/knock-api --timeout=300s
kubectl apply -f k8s/ingress.yaml -f k8s/servicemonitor.yaml -f k8s/networkpolicy.yaml

# 4) 校验
kubectl -n knock-prod get pods -o wide
kubectl -n knock-prod get ingress,pdb,hpa
kubectl -n knock-prod describe certificate knock-prod-tls   # cert-manager 签发的证书
curl -s https://api.knock.example.com/healthz -w "\n%{http_code}\n"
```

`k8s/ingress.yaml` 中的 `knock-prod-tls` 由 cert-manager 依据 `letsencrypt-prod` ClusterIssuer 自动签发；首次签发约 1–3 分钟。

## 6. 回滚

```bash
# 应用回滚：回到上一个 ReplicaSet（保留 5 个历史版本）
kubectl -n knock-prod rollout undo deployment/knock-api
kubectl -n knock-prod rollout status deployment/knock-api --timeout=180s

# 指定版本回滚
kubectl -n knock-prod rollout history deployment/knock-api
kubectl -n knock-prod rollout undo deployment/knock-api --to-revision=3

# 数据库回滚：仅当迁移不可向前兼容时执行，先停写再降级
kubectl -n knock-prod scale deployment/knock-api --replicas=0
kubectl -n knock-prod delete job knock-db-migrate --ignore-not-found
kubectl -n knock-prod run alembic-down --rm -it --image=<上一版本镜像> \
  --restart=Never -- alembic downgrade -1
kubectl -n knock-prod scale deployment/knock-api --replicas=3
```

单机阶段回滚：`docker compose -f docker-compose.prod.yml up -d --no-deps api` 前先把 `.env` 的镜像标签改回上一版，或 `git checkout <上一个 tag> && docker compose up -d --build api`。

## 7. 发布灰度节奏

| 阶段 | 流量 | 观察窗口 | 推进条件 |
| --- | --- | --- | --- |
| 5% | 单 Pod 新版本 | 15 分钟 | 5xx < 0.5%，P95 达标，无 P1 告警 |
| 50% | 半数副本 | 30 分钟 | 错误预算消耗 < 10%，AI 降级率 < 5% |
| 100% | 全量 | 持续观察 2 小时 | 无回滚触发条件 |

AI 链路额外观察 `ai_degraded_total` 与 `breaker_state`，任一异常即回退。

## 8. 与后端的一致性契约

| 项 | 约定值 | 校验点 |
| --- | --- | --- |
| 监听端口 | 8000（容器内） | `configmap.yaml` 的 `PORT`、`deployment.yaml` 的 `containerPort` |
| 探针路径 | `/healthz`（存活）、`/readyz`（就绪） | 均在 8000 根路径，不带 `/api/v1` 前缀 |
| 指标路径 | `/metrics` | `servicemonitor.yaml`、`prometheus.yml` |
| 业务前缀 | `/api/v1` | Nginx `/api/` 透传，后端自行加前缀 |
| 旧接口 | `/api/ai/*`、`/api/health`、`/api/usage`、`/api/selftest` | 灰度期 Nginx 双跑，返回带 `Deprecation` 头 |
| 数据库 | MySQL 8.0，`mysql+aiomysql`，容器内 3306，`?charset=utf8mb4` | `mysql:8.0` 镜像、`DATABASE_URL`、`networkpolicy.yaml` 的 3306 |
| 环境变量 | 见 `env.example` 与 `docs/附录B_环境变量与配置清单.md` | `backend/app/core/config.py` |
| 生产启动命令 | `gunicorn -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000 app.main:app` | `backend/Dockerfile` |

端口或键名任何一侧变更，必须同步修改 `configmap.yaml`、`env.example`、附录 B 三处，否则 Pod 会以 `CrashLoopBackOff` 或探针失败暴露问题。

## 9. 常见问题

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `readyz` 持续 503 | 数据库不可达或 `GLM_API_KEY` 为空 | 查 `kubectl logs` 与 Secret 挂载；先修依赖再重启 |
| 滚动升级卡住 | 新 Pod 就绪探针不通过、`maxUnavailable: 0` 无空位 | `kubectl describe pod` 看事件；必要时 `rollout undo` |
| 证书签发失败 | DNS 未生效或 ACME 挑战被 WAF 拦截 | `kubectl describe certificate,order,challenge`；放行 `/.well-known/acme-challenge/` |
| Grafana 无数据 | Prometheus 未抓到 `/metrics` 或数据源 uid 变化 | 查 `/targets`；确认数据源 uid 为 `prometheus` |
| 静态资源 404 | `static/` 未放构建产物或 index 未刷新 | 重新构建前端并把 `dist/` 挂到 `static/` |

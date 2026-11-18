# 附录B 环境变量与配置清单

本附录列出后端、编排与监控所需的全部环境变量，作为部署、排障与审计的单一依据。键名与 `deliverables/backend/app/core/config.py`（pydantic-settings，大小写不敏感）逐项对应，与 `deliverables/deploy/env.example`、`docker-compose.prod.yml`、`k8s/configmap.yaml`、`k8s/secret.example.yaml` 保持一致。表中"密级"决定存储位置：公开与内部项进 ConfigMap 或 `.env`，机密项只进 Secret 或密钥管理系统。

## B.1 命名约定与读取优先级

配置项统一使用无前缀全大写下划线命名，与旧 Node 版 `server/.env` 中的 `GLM_*` 系列完全同名同义，便于改造期双跑与回退。应用通过 pydantic-settings 读取，读取优先级从高到低为：进程环境变量、容器编排注入的 Secret、ConfigMap 或 `env_file` 指定的文件、代码内默认值。

这个顺序决定了排障时的第一动作：环境变量取到的值与文件中的值不一致时，以注入值为准。Kubernetes 场景下修改 ConfigMap 不会自动生效（容器环境变量在启动时固化），必须执行 `kubectl rollout restart deployment/knock-api`；Compose 场景下修改 `.env` 后需 `docker compose up -d --force-recreate`。

**表 B-1 密级定义与存储位置**

| 密级 | 定义 | 存储位置 | 是否可进镜像 |
| --- | --- | --- | --- |
| 公开 | 泄露无影响，如端口、日志级别 | ConfigMap、环境变量 | 可以 |
| 内部 | 泄露暴露系统结构，如连接串主机名 | ConfigMap（脱敏后）或 Secret | 不建议 |
| 机密 | 泄露导致越权或数据泄露，如密钥、口令 | Secret、密钥管理系统 | 严禁 |

## B.2 应用配置

**表 B-2 应用配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `APP_ENV` | 运行环境标识 | `prod` | 否 | 公开 | `dev` | 决定调试开关、错误详情与鉴权严格度 |
| `DEBUG` | 调试模式 | `false` | 否 | 公开 | `false` | 开启会输出堆栈与 SQL，生产必须关闭 |
| `API_V1_PREFIX` | 业务接口前缀 | `/api/v1` | 否 | 公开 | `/api/v1` | 改动需同步 Nginx 与前端，影响全部业务接口 |
| `PORT` | 容器内监听端口 | `8000` | 否 | 公开 | `8000` | 改动需同步探针、Service、Nginx 上游 |
| `WORKERS` | 工作进程数 | `4` | 否 | 公开 | `4` | 影响并发能力与内存占用；多进程下进程内限流不再全局 |
| `LOG_LEVEL` | 日志级别 | `INFO` | 否 | 公开 | `INFO` | 调到 DEBUG 会显著增加日志量与成本 |
| `LOG_JSON` | 结构化日志开关 | `true` | 否 | 公开 | `true` | 关闭后 Loki 无法按字段检索 |
| `BODY_LIMIT_BYTES` | 请求体上限（字节） | `524288` | 否 | 公开 | `524288` | 与 Nginx `client_max_body_size 2m` 配合，超出返回 413 |
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔 | `https://www.knock.example.com` | 是（生产） | 内部 | 本地三个地址 | 配错会导致前端跨域失败；禁止写 `*` |
| `ALLOWED_HOSTS` | 允许的 Host 头，逗号分隔 | `api.knock.example.com` | 是（生产） | 内部 | `*` | 收紧可防 Host 头攻击，过严会导致 400 |
| `AUTO_CREATE_SCHEMA` | 启动时自动建表 | `false` | 否 | 公开 | `false` | 生产必须关闭，表结构走 Alembic 迁移 |
| `SEED_SCENARIOS_ON_STARTUP` | 启动时补种场景数据 | `true` | 否 | 公开 | `true` | 幂等写入；关闭后新环境需手工导入场景 |

## B.3 数据库配置

**表 B-3 数据库配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `DATABASE_URL` | 主库连接串（asyncpg 驱动） | `postgresql+asyncpg://knock:__PW__@postgres:5432/knock` | 是 | 机密 | 本地 sqlite | 改动即重启；驱动前缀必须是 `postgresql+asyncpg` |
| `DATABASE_READ_URL` | 只读副本连接串，可留空 | 空 | 否 | 机密 | 空 | v1 未启用读写分离，保留键位供二期分流 |
| `DB_POOL_SIZE` | 每进程连接池常驻连接数 | `10` | 否 | 内部 | `10` | 总连接数约等于 `WORKERS × POOL_SIZE`，需与 `max_connections` 对齐 |
| `DB_MAX_OVERFLOW` | 连接池溢出上限 | `20` | 否 | 内部 | `20` | 过大易打满数据库连接，过小会在峰值报池超时 |
| `DB_ECHO` | 打印 SQL | `false` | 否 | 公开 | `false` | 开启会大量输出日志，仅本地排障时短暂打开 |

连接数需要整体核算：4 个 worker、每池 10 常驻加 20 溢出，理论上限 120 条，加上迁移任务、监控与运维会话，需控制在 PG `max_connections=200` 的 80% 以内。若后续调大 `WORKERS`，必须同步下调 `DB_POOL_SIZE`，不能两者同时放大。

## B.4 Redis 配置

**表 B-4 Redis 配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `REDIS_URL` | Redis 连接串，含库号 | `redis://:__PW__@redis:6379/0` | 否 | 机密 | 空（退回进程内） | 留空则不崩但限流与配额只在单进程内生效；多副本时必须配置 |

Redis 承载四类状态：限流计数、日配额、AI 结果缓存、refresh token 撤销黑名单。`REDIS_URL` 为空时后端自动退回进程内实现，单机可用、多副本失效——这是有意的降级设计，保证"缺依赖不崩"，但生产三副本必须配置 Redis，否则全局配额与限流形同虚设。

## B.5 AI 网关配置

**表 B-5 AI 网关配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `GLM_API_KEY` | 智谱开放平台密钥 | `__CHANGE_ME__` | 是（生产） | 机密 | 空 | 为空时全站回落规则评分，`/readyz` 报未就绪 |
| `GLM_BASE_URL` | 对话补全接口地址 | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | 否 | 内部 | 同示例 | 换网关或代理时修改；禁止指向不可信域名 |
| `GLM_MODEL` | 主模型 | `glm-4.7-flash` | 否 | 内部 | `glm-4.7-flash` | 换模型影响延迟、成本与评分风格 |
| `GLM_FALLBACK_MODELS` | 降级模型链，逗号分隔 | `glm-4.5-flash,glm-4-flash` | 否 | 内部 | 同示例 | 主模型失败时按序尝试，链越长单次耗时上限越高 |
| `GLM_TIMEOUT_MS` | 单次调用超时（毫秒） | `45000` | 否 | 内部 | `45000` | 必须小于前端 60 秒超时，否则前端先断 |
| `GLM_DAILY_CAP` | 全局日调用上限 | `800` | 否 | 内部 | `800` | 触顶后全站降级；调整需评估成本 |
| `GLM_RPM_PER_IP` | 单 IP 每分钟调用上限 | `20` | 否 | 内部 | `20` | 过低误伤正常用户，过高易被刷量 |
| `GLM_CONCURRENCY` | 全局并发上限 | `2` | 否 | 内部 | `2` | 与 Pod 数相乘决定供应商侧并发压力 |
| `GLM_CACHE_TTL_SEC` | AI 结果缓存时长（秒） | `600` | 否 | 内部 | `600` | 缓存越长命中率越高，但内容时效性下降 |
| `GLM_CACHE_MAX` | 缓存条目上限 | `300` | 否 | 内部 | `300` | 影响 Redis 内存占用与命中率 |
| `GLM_BREAKER_FAILURE_THRESHOLD` | 熔断失败率阈值 | `0.5` | 否 | 内部 | `0.5` | 调低更易熔断（更保守），调高更激进 |
| `GLM_BREAKER_MIN_SAMPLES` | 熔断最小样本数 | `10` | 否 | 内部 | `10` | 样本太小会被偶发失败触发 |
| `GLM_BREAKER_OPEN_SEC` | 熔断保持打开时长（秒） | `30` | 否 | 内部 | `30` | 决定半开探测频率 |
| `GLM_MAX_RETRIES` | 失败重试次数（仅 429/5xx/超时） | `1` | 否 | 内部 | `1` | 重试提高成功率但放大延迟与成本 |

AI 变量之间有三处约束必须同时满足：`GLM_TIMEOUT_MS` 小于前端 60 秒超时；重试次数与超时相乘不超过入口 60 秒代理超时；`GLM_CONCURRENCY × 副本数` 不超过供应商账户的并发配额。任何一项被单独调整都可能引发超时雪崩。

## B.6 安全配置

**表 B-6 安全配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `JWT_SECRET` | 令牌签名密钥 | 64 位随机串 | 是（生产） | 机密 | 开发默认值 | 更换后全部已签发令牌失效，需提前通告 |
| `JWT_ALGORITHM` | 签名算法 | `HS256` | 否 | 公开 | `HS256` | 改为非对称算法需同时下发公钥，属架构变更 |
| `JWT_ACCESS_TTL_MIN` | 访问令牌有效期（分钟） | `30` | 否 | 内部 | `30` | 越短越安全但刷新更频繁 |
| `JWT_REFRESH_TTL_DAYS` | 刷新令牌有效期（天） | `7` | 否 | 内部 | `7` | 越长越便利，失窃风险窗口也越长 |
| `JWT_GUEST_TTL_HOURS` | 访客令牌有效期（小时） | `24` | 否 | 内部 | `24` | 影响未登录试用体验 |
| `ARGON2_TIME_COST` | 口令哈希迭代次数 | `3` | 否 | 公开 | `3` | 提高更抗暴力破解但登录更慢 |
| `ARGON2_MEMORY_COST` | 口令哈希内存（KB） | `65536` | 否 | 公开 | `65536` | 64 MB/次，需核算登录峰值内存 |
| `ARGON2_PARALLELISM` | 口令哈希并行度 | `4` | 否 | 公开 | `4` | 与 CPU 核数匹配，过高会挤占业务 |

`JWT_SECRET` 的生成与保管是本表中风险最高的一项：必须用密码学随机源生成不少于 32 字节，生产环境只存在于 Secret 中，轮换采用"双密钥并行验签"过渡（新令牌用新密钥签名，旧密钥保留一个 refresh 周期用于验签），确认旧令牌自然过期后再移除旧密钥。禁止在日志、镜像、提交历史中出现该值。

## B.7 可观测配置

**表 B-7 可观测配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `OTEL_ENABLED` | 是否启用追踪 | `true` | 否 | 公开 | `false` | 关闭后只有指标与日志，排障定位变慢 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP 上报地址 | `http://otel-collector.observability.svc.cluster.local:4317` | 否 | 内部 | 空 | 配错会导致追踪丢失但不影响业务 |
| `OTEL_SERVICE_NAME` | 追踪中的服务名 | `knock-backend` | 否 | 公开 | `knock-backend` | 改动会断开历史链路对比 |
| `SENTRY_DSN` | 异常上报地址 | 空 | 否 | 机密 | 空 | 未安装 SDK 时忽略；启用后会上报堆栈 |

## B.8 限流配置

**表 B-8 限流配置变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `RATE_LIMIT_ENABLED` | 应用层限流开关 | `true` | 否 | 公开 | `true` | 关闭后仅剩 Nginx 层限流，AI 成本失控风险上升 |
| `RATE_LIMIT_WINDOW_SEC` | 限流窗口（秒） | `60` | 否 | 内部 | `60` | 与 `GLM_RPM_PER_IP` 共同决定单 IP 配额 |

应用层限流与 Nginx 层限流是两道独立防线，不是重复：Nginx 按连接与请求速率拦突发，应用层按用户与业务维度拦滥用。压测时关闭应用层限流以测量真实容量，生产必须开启。

## B.9 二期预留变量

以下变量在当前版本（v1）中不被读取，仅为二期功能预留键位，**不得写入 v1 的必填清单**，否则会误导部署人员。

**表 B-9 二期预留变量**

| 变量名 | 含义 | 示例值 | 必填 | 密级 | 默认值 | 变更影响 |
| --- | --- | --- | --- | --- | --- | --- |
| `FIELD_ENCRYPTION_KEY` | 敏感字段加密主密钥（32 字节） | 随机串 | 否 | 机密 | 空 | 二期启用字段级加密后必填，v1 忽略 |
| `SMTP_HOST` | 邮件服务器地址 | `smtp.example.com` | 否 | 内部 | 空 | 二期用于通知与找回口令 |
| `SMTP_PORT` | 邮件服务器端口 | `465` | 否 | 公开 | `465` | 二期使用 |
| `SMTP_USER` | 邮件账号 | `noreply@example.com` | 否 | 内部 | 空 | 二期使用 |
| `SMTP_PASSWORD` | 邮件授权码 | `__CHANGE_ME__` | 否 | 机密 | 空 | 二期使用 |
| `SMTP_FROM` | 发件人显示地址 | `noreply@example.com` | 否 | 内部 | 空 | 二期使用 |

## B.10 编排侧变量

以下变量不属于应用配置，仅由 Docker Compose 或监控栈消费，不得与业务变量混用。

**表 B-10 编排与监控侧变量**

| 变量名 | 归属 | 含义 | 示例值 | 密级 |
| --- | --- | --- | --- | --- |
| `POSTGRES_DB` | postgres 镜像 | 初始化数据库名 | `knock` | 内部 |
| `POSTGRES_USER` | postgres 镜像 | 初始化超级用户 | `knock` | 内部 |
| `POSTGRES_PASSWORD` | postgres 镜像 | 超级用户口令 | `__CHANGE_ME__` | 机密 |
| `REDIS_PASSWORD` | redis 镜像 | 实例口令 | `__CHANGE_ME__` | 机密 |
| `GRAFANA_ADMIN_USER` | grafana 镜像 | 管理员账号 | `admin` | 内部 |
| `GRAFANA_ADMIN_PASSWORD` | grafana 镜像 | 管理员口令 | `__CHANGE_ME__` | 机密 |

## B.11 三套环境的取值差异

同一份变量清单在三套环境中只有取值不同，键名不变。这样做的目的是让"部署到预发"与"部署到生产"使用同一套模板，减少因键名漂移导致的配置错误。

**表 B-11 dev/staging/prod 取值对照**

| 变量名 | dev | staging | prod |
| --- | --- | --- | --- |
| `APP_ENV` | `dev` | `staging` | `prod` |
| `DEBUG` | `true` | `false` | `false` |
| `DATABASE_URL` | 本地 sqlite 或本地 PG | 预发 PG（脱敏数据） | 生产 PG（主从） |
| `REDIS_URL` | 可留空 | 预发 Redis | 生产 Redis（哨兵） |
| `CORS_ORIGINS` | 本地 5173/8787 | 预发域名 | `https://www.knock.example.com` |
| `ALLOWED_HOSTS` | `*` | 预发域名 | 生产域名 |
| `AUTO_CREATE_SCHEMA` | `true` | `false` | `false` |
| `OTEL_ENABLED` | `false` | `true` | `true` |
| `GLM_DAILY_CAP` | `50` | `200` | `800` |
| `RATE_LIMIT_ENABLED` | `false` | `true` | `true` |

预发环境的数据脱敏规则必须与生产一致，但内容为生产数据的抽样替换版本：姓名、手机号、对话原文全部替换为合成值，保留数据分布特征以便压测与页面联调。禁止把生产库快照直接复制到预发。

## B.12 配置变更纪律

配置变更与代码变更同等对待，走同一条发布通道。三条纪律：

一是任何配置变更都要留痕：变更单记录改了什么、为什么改、影响哪些服务、回滚方式。ConfigMap 与 Secret 的修改必须经由 Git 中的清单文件，禁止在生产集群里直接 `kubectl edit`，否则下一次 apply 会覆盖掉手工修改，形成"临时修好了、发布后又坏了"的循环。

二是变更后必须验证三件事：启动日志中配置摘要不含真实密钥（`safe_summary` 只输出 `configured: true/false`）、`/readyz` 返回 200、关键链路冒烟通过。仅看 Pod 变为 Running 不足以为证。

三是敏感配置的读取与传递最小化：读取 `.env` 或 Secret 的权限仅授予运维角色；CI 中使用仓库 Secret 而非硬编码；导出配置用于排障时先做脱敏，删掉全部机密项。附录 B 中所有"机密"级变量的真实值只存在于部署环境的 Secret 中，本文档与任何交付目录中都不含真实值。

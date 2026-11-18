# 附录C 代码规范与目录结构

本附录给出后端代码的组织方式与工程约束，供后续维护者与评审者对照执行。目录树、分层依赖、命名约定与静态检查规则均与仓库内 `deliverables/backend/pyproject.toml`、`Makefile` 保持一致，CI 可直接按本附录的命令执行检查，不需要额外的口头约定。

代码规模以实测为准：Python 文件 81 个、10,904 行，其中应用代码 59 个文件 8,596 行，测试 14 个文件 1,394 行，脚本 5 个文件 536 行，迁移 3 个文件 378 行。

## C.1 目录结构

后端采用按层分包的扁平结构，每一层只依赖其下层，跨层调用通过服务函数显式完成，不使用全局单例。

```text
backend/
├── app/
│   ├── main.py                 # create_app 工厂与 lifespan
│   ├── api/                    # 传输层：路由、依赖注入、兼容层
│   │   ├── deps.py
│   │   ├── legacy.py
│   │   └── v1/{auth,scenarios,sessions,stats,ai,health,router}.py
│   ├── core/                   # 横切：配置、安全、日志、错误、指标
│   ├── domain/                 # 领域：枚举、ORM 模型、Schema、规则与评分
│   ├── services/               # 应用服务：编排、AI 网关、审计、统计
│   │   └── llm/                # 模型层：Provider、路由、缓存、熔断、配额
│   ├── prompts/                # 四条链路提示词与解析器
│   ├── infra/                  # 基础设施：数据库、会话、Redis、缓存
│   └── tasks/                  # 预留：周期任务，本期为空
├── alembic/                    # 迁移环境与 0001 初始迁移
├── tests/                      # pytest 用例与共享夹具
├── scripts/                    # 初始化、文档生成、冒烟、排查
├── Dockerfile  docker-compose.yml  Makefile  requirements.txt  pyproject.toml
```

**表 C-1 分层职责与允许的依赖方向**

| 层 | 目录 | 职责 | 允许依赖 |
| --- | --- | --- | --- |
| 传输层 | `app/api/` | 解析请求、鉴权、限流、调用服务、拼响应包 | services、domain、core |
| 服务层 | `app/services/` | 业务编排、事务边界、AI 调用与降级 | domain、infra、prompts、core |
| 模型层 | `app/services/llm/` | Provider 抽象、模型链、缓存、熔断、配额 | core、infra |
| 领域层 | `app/domain/` | 纯函数规则、评分、危机判定、数据结构 | core（仅枚举与错误） |
| 提示词 | `app/prompts/` | 提示词拼装与输出解析 | domain、core |
| 基础设施 | `app/infra/` | 连接、会话、KV 与缓存实现 | core |
| 横切 | `app/core/` | 配置、日志、指标、错误码、安全原语 | 无业务依赖 |

## C.2 命名与分层约束

命名遵循 Python 社区惯例并补充项目约定：模块与函数用小写下划线，类用大驼峰，常量用大写，私有成员以单下划线开头；同一概念在四层保持同名，避免出现「模型叫会话、服务叫对话、接口叫练习」的三套叫法。

**表 C-2 命名约定**

| 对象 | 约定 | 示例 |
| --- | --- | --- |
| 模块 | 小写蛇形，按职责单数命名 | `session_service.py` |
| 类 | 大驼峰，后缀表明角色 | `ModelRouter`、`CircuitBreaker` |
| 函数 | 动词开头，返回布尔用 `is_`、`has_` | `compute_rule_score` |
| 路由函数 | 与资源动作一致，返回 Pydantic 模型 | `create_session` |
| 常量 | 全大写，模块级 | `MERGE_RATIO` |
| 依赖项 | `xxx_dep` 或类型别名 | `CurrentUser`、`GatewayDep` |

分层约束以「可 import 性」表达，评审时按表 C-3 检查。违反方向的调用即使能运行也应在评审中退回，因为反向依赖会让领域层难以单测，也会让 AI 网关被业务逻辑污染。

**表 C-3 分层禁止项**

| 禁止项 | 原因 |
| --- | --- |
| `domain` 导入 `services` 或 `infra` | 领域函数必须可在无数据库、无网络的进程内运行 |
| `infra` 导入 `api` | 连接层不应知道 HTTP 细节 |
| 路由内直接建数据库会话或调用 Provider | 事务与降级逻辑必须集中在服务层 |
| 在 `core` 中出现业务名词 | 横切模块应可整体复用到其他项目 |
| 模块级可变全局状态 | 多 worker 部署下进程内状态不可共享，状态一律经 `app.state` 注入 |

## C.3 静态检查规则

静态检查由 ruff 与 mypy 承担，规则集写在 `pyproject.toml`，不在命令行追加参数，保证本地与 CI 一致。

**表 C-4 ruff 规则集**

| 规则组 | 含义 | 取舍 |
| --- | --- | --- |
| E、F | pycodestyle 错误与 pyflakes | 全开，未使用导入与未定义名称必须为零 |
| I | 导入排序 | 全开，标准库、第三方、本包三段 |
| UP | 语法升级 | 全开，按 Python 3.12 写法 |
| B | bugbear | 全开，拦截可变默认参数等常见缺陷 |
| SIM | 简化建议 | 全开，但忽略 `SIM105`（`contextlib.suppress` 与显式 try 等价时保留可读性） |
| ASYNC | 异步误用 | 全开，拦截异步函数中的阻塞调用与未 await 协程 |
| 行宽 | 100 字符 | `E501` 忽略，长字符串与 URL 不强制折行 |
| 格式化 | 双引号 | 由 `ruff format` 统一，不手工调整 |

mypy 开启 `disallow_untyped_defs`、`disallow_incomplete_defs`、`no_implicit_optional`、`check_untyped_defs`，即应用代码的每个函数都必须有完整类型标注；测试目录通过 overrides 放宽，允许省略返回类型以保持用例简洁。Pydantic 模型通过官方插件检查字段类型与构造调用。`alembic/versions/` 由自动生成，排除检查。

检查命令与失败处理：

```bash
python -m ruff check app tests scripts   # 必须零告警
python -m ruff format --check app tests scripts
python -m mypy app                       # 必须零错误
python -m pytest -q                      # 162 个用例必须全绿
```

## C.4 测试规范

测试只依赖进程内组件：数据库用 SQLite 异步内存库，缓存用内存实现，模型用假 Provider，因此无需启动 PostgreSQL、Redis 与真实模型即可全量运行。用例文件按被测面划分，一个文件对应一类契约，避免出现「大杂烩」测试文件。

**表 C-5 用例组织**

| 文件 | 覆盖对象 | 用例数 |
| --- | --- | --- |
| `test_health.py` | 健康检查、指标、请求标识 | 5 |
| `test_auth.py` | 登录、刷新轮换、撤销、游客权限 | 10 |
| `test_scenarios.py` | 案例与知识卡读取 | 3 |
| `test_domain_rules.py` | 词表、八步判定、意图分类 | 11 |
| `test_domain_scoring.py` | 权重、规则分、融合、弱点 | 13 |
| `test_security.py` | 哈希、令牌、脱敏、缓存键 | 8 |
| `test_ai.py` | 四条链路成功与降级、配额、危机拦截 | 11 |
| `test_sessions.py` | 会话生命周期、幂等、越权、状态冲突 | 9 |
| `test_legacy.py` | 旧接口形状与弃用头 | 8 |
| `test_stats.py` | 统计与热力图 | 4 |
| `test_ratelimit.py` | 窗口限流与转发头 | 4 |

用例命名采用 `test_<行为>_<预期>` 的形式，断言以响应包内的错误码与数据结构为主，不以 HTTP 状态码单独作为判据，因为错误码表才是前端契约。涉及 AI 的用例必须显式安装假 Provider 并断言调用次数，危机拦截用例断言调用次数为零，这是铁律的可执行证明。

## C.5 提交与评审

提交信息采用「类型(范围): 说明」的格式，类型限定为 feat、fix、refactor、test、docs、chore、perf 七种，范围取模块名如 `ai-gateway`、`sessions`、`docs`。一次提交只做一件事，迁移文件与模型改动必须同一次提交，提示词改动必须同时提升版本号，否则缓存会读到旧结果。

**表 C-6 评审清单**

| 检查项 | 通过标准 |
| --- | --- |
| 分层依赖 | 未出现表 C-3 的禁止项 |
| 错误处理 | 新增失败路径返回统一错误码，不抛裸异常给页面 |
| 降级分支 | AI 调用失败有规则或模板兜底，接口不返回空数据 |
| 危机铁律 | 危机路径无模型调用，且有测试断言 |
| 归属校验 | 新增读写接口均按账号过滤，越权返回 40301 |
| 幂等 | 写接口支持客户端标识去重，重复请求结果一致 |
| 可观测 | 新链路补齐指标与日志字段，日志不含原文与凭据 |
| 迁移 | 模型变更附带迁移，`alembic check` 无漂移 |
| 文档 | 接口或配置变更同步更新第 5、6 章与附录 A |

评审以「可运行、可复算、可回滚」为底线：可运行指按 README 能在八分钟内起服务并跑通冒烟；可复算指评分与统计结果能用规则代码重算一致；可回滚指数据库迁移与应用版本各自可退回上一个发布。三项中有任一项无法验证时，评审不通过。

# 附录A API 接口清单

本清单由 `deliverables/backend/scripts/gen_api_doc.py` 读取运行中应用的 `app.openapi()` 自动生成，方法、路径、请求字段与响应码均取自 OpenAPI 文档，角色列对应第 5 章的 RBAC 矩阵。

接口总数：52 条；统一前缀 `/api/v1`，健康检查与指标端点位于根路径。

## A.1 通用响应包与错误码

除旧版兼容接口外，所有接口返回统一响应包 `{code, message, data, request_id}`；`code=0` 表示成功，非 0 时 `data` 为 null，HTTP 状态码与错误码一一对应。

**表 A-1 统一错误码**

| code | HTTP | 含义 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40001 | 400 | 参数校验失败 |
| 40101 | 401 | 未认证或令牌失效 |
| 40301 | 403 | 无权限（含越权访问他人数据） |
| 40401 | 404 | 资源不存在 |
| 40901 | 409 | 状态冲突（会话已结束等） |
| 42901 | 429 | 单 IP 窗口限流 |
| 42902 | 429 | AI 每日配额耗尽 |
| 50301 | 503 | AI 能力不可用 |
| 50001 | 500 | 服务内部错误 |

## A.2 接口明细

### 运维

**表 A-2 运维接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/healthz` | 公开 | 无需鉴权 | — | 200 | 存活探针 |
| GET | `/readyz` | 公开 | 无需鉴权 | — | 200 | 就绪探针 |

### 认证

**表 A-3 认证接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/auth/me` | Bearer | 任意角色 | — | 200 | 读取当前账号 |
| POST | `/api/v1/auth/guest` | 公开 | 游客只读体验（新增能力） | nickname?:object | 200、422 | 创建游客账号 |
| POST | `/api/v1/auth/login` | 公开 | 按用户名密码换令牌 | username:string、password:string | 200、422 | 账号密码登录 |
| POST | `/api/v1/auth/logout` | Bearer | 任意角色 | — | 200 | 登出并撤销令牌 |
| POST | `/api/v1/auth/refresh` | 公开 | refresh 令牌换新令牌对 | refresh_token:string | 200、422 | 刷新访问令牌 |

### 案例与知识卡

**表 A-4 案例与知识卡接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/knowledge/cards` | 公开 | 技巧卡 | — | 200、422 | 技巧卡列表 |
| GET | `/api/v1/scenarios` | 公开 | 案例目录 | — | 200、422 | 案例列表 |
| GET | `/api/v1/scenarios/{scenario_id}` | 公开 | 案例详情 | — | 200、422 | 案例详情 |

### 训练会话

**表 A-5 训练会话接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/sessions` | Bearer | 仅本人数据，游客可读 | — | 200、422 | 我的会话列表 |
| GET | `/api/v1/sessions/{session_id}` | Bearer | 仅会话所有者 | — | 200、422 | 会话详情 |
| POST | `/api/v1/sessions` | Bearer | 正式用户（游客 40301） | scenario_id:string、difficulty?:object、blindfold?:boolean、max_turns?:integer、client_session_id?:object | 200、422 | 创建训练会话 |
| POST | `/api/v1/sessions/{session_id}/debrief` | Bearer | 会话所有者 | — | 200、422 | 生成三段式复盘 |
| POST | `/api/v1/sessions/{session_id}/finish` | Bearer | 会话所有者 | — | 200、422 | 结案并写入训练记录 |
| POST | `/api/v1/sessions/{session_id}/stages/{stage_index}/score` | Bearer | 会话所有者 | — | 200、422 | 分段评分 |
| POST | `/api/v1/sessions/{session_id}/turns` | Bearer | 会话所有者 | text:string、client_turn_id?:object、stage?:object | 200、422 | 提交一句学生发言并取得角色回应 |
| DELETE | `/api/v1/sessions/{session_id}` | Bearer | admin | — | 200、422 | 删除会话（管理员） |

### 统计

**表 A-6 统计接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/stats/heatmap` | Bearer | 仅本人数据 | — | 200、422 | 训练热力图 |
| GET | `/api/v1/stats/me` | Bearer | 仅本人数据 | — | 200 | 我的训练看板 |

### AI 链路

**表 A-7 AI 链路接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/ai/debrief` | 公开 | 按 IP 限流 | session_id?:object、scores?:object、hit_rules?:string[]、nickname?:string | 200、422 | 三段式复盘 |
| POST | `/api/v1/ai/intent` | 公开 | 旧前端同源调用，按 IP 限流 | input:string、stage?:object、scenario_id?:object、session_id?:object | 200、422 | 判定学生意图 |
| POST | `/api/v1/ai/persona` | 公开 | 按 IP 限流 | scenario_id:string、emotion?:integer、history?:object[]、said_lines?:string[]、phase?:object、difficulty?:object、session_id?:object | 200、422 | 生成角色台词 |
| POST | `/api/v1/ai/score` | 公开 | 按 IP 限流 | dialogue?:object[]、session_id?:object、stage_index?:integer、completed_stages?:integer、total_stages?:integer | 200、422 | 六维评分 |

### 教师端

**表 A-8 教师端接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/teacher/learners` | Bearer | 仅名下学员 | — | 200 | 名下学员列表 |
| GET | `/api/v1/teacher/learners/{owner_id}/records` | Bearer | 跨班返回空集 | — | 200、422 | 查看学员训练记录 |
| GET | `/api/v1/teacher/stats` | Bearer | 班级聚合看板 | — | 200 | 班级看板 |
| POST | `/api/v1/teacher/learners` | Bearer | 绑定学员到名下 | username:string | 200、422 | 绑定学员到名下 |

### 管理端

**表 A-9 管理端接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/accounts` | Bearer | 账号列表 | — | 200、422 | 账号列表 |
| GET | `/api/v1/admin/ai-logs` | Bearer | AI 调用审计 | — | 200、422 | AI 调用审计日志 |
| GET | `/api/v1/admin/overview` | Bearer | 运行概览与配额 | — | 200 | 运行概览 |
| GET | `/api/v1/admin/rule-words` | Bearer | 词表分组与自定义词 | — | 200 | 判定词表（分组与自定义词） |
| GET | `/api/v1/admin/script-lines` | Bearer | 台词节点列表 | — | 200、422 | 台词节点列表 |
| POST | `/api/v1/admin/accounts` | Bearer | 教务导入建号 | username:string、password:string、nickname?:object、role?:string | 200、422 | 新建账号（教务导入） |
| POST | `/api/v1/admin/cards` | Bearer | 新建或编辑技巧卡 | id:string、title?:object、category?:object、summary?:object、content?:object、tags?:object、stage?:object、order_index?:object | 200、422 | 新建或编辑技巧卡 |
| POST | `/api/v1/admin/rule-words` | Bearer | 追加词条 | group:string、word:string、note?:string | 200、422 | 追加词条 |
| POST | `/api/v1/admin/scenarios` | Bearer | 新建或编辑案例 | id:string、name?:object、age?:object、gender?:object、archetype?:object、resistance?:object、difficulty?:object、sensitive_tag?:object、brief?:object、initial_emotion?:object、system_prompt?:object、voice_low?:object、voice_mid?:object、voice_high?:object、forbidden?:object、active?:object | 200、422 | 新建或编辑案例 |
| POST | `/api/v1/admin/script-lines` | Bearer | 新增台词 | text:string、emotion_bucket?:string、scenario_id?:object、order_index?:integer | 200、422 | 新增台词 |
| DELETE | `/api/v1/admin/cards/{card_id}` | Bearer | 删除技巧卡 | — | 200、422 | 删除技巧卡 |
| DELETE | `/api/v1/admin/rule-words/entry/{word_id}` | Bearer | 删除自定义词条 | — | 200、422 | 删除自定义词条 |
| DELETE | `/api/v1/admin/rule-words/{group}/{word}` | Bearer | 禁用词条（危机组禁止） | — | 200、422 | 禁用词条 |
| DELETE | `/api/v1/admin/scenarios/{scenario_id}` | Bearer | 下架案例 | — | 200、422 | 下架案例 |
| DELETE | `/api/v1/admin/script-lines/{line_id}` | Bearer | 删除台词 | — | 200、422 | 删除台词 |
| PATCH | `/api/v1/admin/accounts/{account_id}/active` | Bearer | 启用 / 停用 | active:boolean | 200、422 | 启用 / 停用账号 |
| PATCH | `/api/v1/admin/script-lines/{line_id}` | Bearer | 编辑台词 | text?:object、emotion_bucket?:object、order_index?:object、active?:object | 200、422 | 编辑台词 |

### 兼容层

**表 A-10 兼容层接口**

| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/health` | 公开 | 旧版，Deprecated | — | 200 | 旧版健康检查 |
| GET | `/api/usage` | 公开 | 旧版，Deprecated | — | 200 | 旧版用量查询 |
| POST | `/api/ai/debrief` | 公开 | 旧版，Deprecated | — | 200、422 | 旧版复盘报告 |
| POST | `/api/ai/intent` | 公开 | 旧版，Deprecated | — | 200、422 | 旧版意图判定 |
| POST | `/api/ai/persona` | 公开 | 旧版，Deprecated | — | 200、422 | 旧版角色扮演 |
| POST | `/api/ai/score` | 公开 | 旧版，Deprecated | — | 200、422 | 旧版六维评分 |
| POST | `/api/selftest` | 公开 | 旧版，Deprecated | — | 200 | 旧版链路自检 |

## A.3 鉴权与限流约定

- `Authorization: Bearer <access_token>`：access 令牌有效期 30 分钟，refresh 令牌 7 天且一次性轮换（旧 refresh 立即撤销）。
- 游客令牌 24 小时有效，仅可读取案例、知识卡与本人会话，写操作返回 40301。
- `/api/v1/ai/*` 与旧版 `/api/ai/*` 按单 IP 每分钟 20 次限流，超限返回 42901；AI 每日 800 次配额耗尽返回 42902。
- 旧版接口响应附带 `Deprecation`、`Sunset`、`Link` 与 `X-Knock-Api: legacy` 头，响应体保持旧形状，便于前端灰度切换。

# FACTS —— 全队唯一数字来源

> 规则：正文引用的任何数字都必须能在本文件找到。新增数字先在"待核验"区记录核实过程，再上移到"已确认"区。
> 路径基准：`F:\毕业设计\src_extract\01_作品及成果文件\`（下称"源码目录"）。
> 最近核验：2026-11-12，analyst 完成 D/E 区实测，I 区条目已全部上移。

## A 项目标识（已确认）

| 项 | 值 |
|---|---|
| 项目名 | 叩门 · 社工个案面谈 AI 陪练舱 |
| 作品版本 | package.json `version: 1.1.0` |
| 依据标准 | 民政部《社会工作方法 个案工作》（公告第 426 号） |
| 交付包 | `叩门·社工个案面谈 AI 陪练舱_471188.zip`（压缩包 106,990,135 字节，5,138 个条目） |
| 压缩包内有效源码 | 70 个文件（剔除 node_modules 5,039 项、dist 7 项、演示视频 1 项） |

## B 代码规模（已确认，`wc -l` 实测）

| 模块 | 文件数 | 行数 | 说明 |
|---|---|---|---|
| `src/`（前端 TypeScript/TSX/CSS） | 36 | 12,893 | 含 data/services/lib/pages/hooks/components |
| ├ `src/data/` | 7 | 2,463 | 内容层：角色/台词树/技巧卡/剧本生成 |
| ├ `src/services/` | 4 | 1,856 | rules 568 / dialogueEngine 567 / scoring 522 / crisis 199 |
| ├ `src/lib/` | 4 | 1,066 | aiClient 433 / db 432 / backendCheck 140 / debriefStore 61 |
| ├ `src/pages/` | 11 | 2,990 | TrainingPage 749 为最大页面 |
| ├ `src/hooks/useSession.ts` | 1 | 513 | 训练会话状态机 |
| ├ `src/components/Tour.tsx` | 1 | 270 | 引导组件 |
| └ 其余（App/types/main/css） | 8 | 1,735 | App 275 / types 262 等 |
| `server/`（Node 后端） | 3 | 1,046 | index.mjs 411 / glm.mjs 327 / prompts.mjs 308 |
| `supabase/migrations/` | 2 | 472 | 001_schema 199 / 002_supplements 273 |
| `supabase/functions/wenxin-text-generation/index.ts` | 1 | 280 | Deno Edge Function（参考实现） |
| `tools/`（开发期自检 Python） | 7 | 753 | validate/check_paths/check_consistency 等 |
| 合计（不含 node_modules/dist） | 70 | 16,331 | 12,893 + 1,046 + 472 + 280 + 753 + 其余配置 |

## C 运行时事实（已确认）

| 项 | 值 | 证据 |
|---|---|---|
| Node 版本要求 | `>=18.17`，推荐 20 LTS | package.json engines |
| 服务端口 | 8787（`PORT` 可改） | `server/glm.mjs:59` |
| HTTP 框架 | Node 内置 `node:http`，零第三方运行时依赖 | `server/index.mjs:13` |
| 静态托管 | 同进程托管 `dist/`，SPA fallback 到 index.html | `server/index.mjs:223-274` |
| 请求体上限 | 512 KB | `server/index.mjs:48` |
| CORS 白名单 | 仅 `localhost/127.0.0.1/[::1]` | `server/index.mjs:52-62` |
| 客户端 IP 判定 | 无条件取 `x-forwarded-for` 首段 | `server/index.mjs:354-358` |
| 进程内限流 | 单 IP 20 次/分钟（内存滑动窗口，重启清零） | `server/glm.mjs:103-116` |
| 全局并发 | 2（进程内信号量） | `server/glm.mjs:118-131` |
| 日调用上限 | 800 次（进程内存计数，重启清零） | `server/glm.mjs:185-187`、`:89-100` |
| 结果缓存 | 内存 Map，TTL 10 分钟，容量 300 | `server/glm.mjs:135-155` |
| 模型 | `glm-4.7-flash`；降级 `glm-4.5-flash → glm-4-flash` | `server/glm.mjs:44-49` |
| 关闭思维链 | 请求体固定 `thinking:{type:"disabled"}` | `server/glm.mjs:199` |
| 单次超时 | 45,000 ms（全链路统一，无分级） | `server/glm.mjs:51` |
| 前端 AI 超时 | 60,000 ms（意图链路 15,000 ms） | `src/lib/aiClient.ts:19-24` |
| 前端构建 | Vite 5.4.9 + tsc，产物 `dist/` | package.json |
| 启动方式 | `start.bat` / `start.sh`：检查 Node → 安装 → 构建 → 启动 | `start.bat`、`start.sh` |
| 本地账号口令 | djb2 变体 32 位哈希、无盐、无迭代 | `src/store/store.tsx:91-95` |
| 游客态 | 无。未登录仅可访问 `/`、`/login`、`/about`、`/knowledge` | `src/App.tsx:184-196` |

## D 业务内容资产（已核实，analyst 2026-11-12 实测，以源码为准）

| 资产 | 核实值 | 证据 |
|---|---|---|
| 服务对象角色 | 12 位 | `src/data/scenarios.ts:10-155`（SCENARIOS 12 项）；`src/data/personas.ts`（PERSONAS 12 份，每份 systemPrompt 均 >200 字） |
| 台词节点 | 118 个 / 354 句 | `src/data/dialogueTree.ts`（46 个）+ `src/data/dialogueTreeExtra.ts`（72 个），每节点 3 情绪变体 |
| 节点分布 | W-01 16 个；L-02、C-03、Z-04、U-05、A-06 各 6 个；G-07、M-08、B-09、F-10、S-11、H-12 各 12 个 | `tools/validate.py` 实跑输出 |
| 技巧卡 | 19 张（T-01～T-19） | `src/data/knowledge.ts:23-231` |
| 伦理守则 | 11 条 + 1 条边界声明，共 12 个数组项 | `src/data/knowledge.ts:244-343`；第 12 项 code 为 `—`，标题"工具不承担安全评估" |
| 阻抗形态 | 6 种 | `src/data/knowledge.ts:349-398`（RESISTANCE_NOTES） |
| 判定词表 | **165 条九表 + 6 条封闭提问后缀 = 171 条** | `src/services/rules.ts:60-191`；同感 16 / 开放提问 22 / 评判 30 / 建议过早 17 / 沉默陪伴 9 / 离题 16 / 危机 29 / 无望感 17 / 毒性积极 9；另有 `CLOSED_QUESTION_SUFFIX` 6 条（吗/吧/对吧/是不是/有没有/好不好） |
| 判定步骤 | 8 步，顺序：危机 → 评判 → 建议过早 → 离题 → 沉默陪伴 → 共情 → 开放式提问 → 封闭式提问 | `src/services/rules.ts:197-212`（注释）、`:328-472`（实现）；空输入另计沉默陪伴 `:441-453` |
| 六维权重 | 同感 25 / 提问 20 / 建议 15 / 伦理 20 / 过程 10 / 风险 10，合计 100 | `src/services/scoring.ts:23-74`、`server/prompts.mjs:12-55` |
| 规则底分 | 六维初值 60，伦理 70；`judgeCount>0` 伦理封顶 60；空泛共情 ≥2 句同感封顶 50；无望感未识别风险封顶 55；识别 +10；过程分 = 已完成阶段/总阶段 × 100；末端统一 clamp 0-100 | `src/services/scoring.ts:125-193` |
| 综合分公式 | 规则分 × 0.4 + AI 分 × 0.6 | `src/services/scoring.ts:310-343`（`mergeScores` 默认 `ratio{rule:0.4,ai:0.6}`） |
| AI 评分作废条件 | 六维任一缺失或非法，整条 AI 结果作废，仅用规则分 | `src/services/scoring.ts:333-336` |
| 训练阶段 | 内容层 5 阶段（rapport/explore/assess/link/close），UI 合并 3 段 | `src/types.ts:76-87`、`src/hooks/useSession.ts:62-66` |
| 难度档位 | 3 档：简单实习/标准实训/挑战督导 | `src/types.ts`、`002_schema_supplements.sql` check 约束 |
| AI 参与度 | 3 档 `rule`/`hybrid`/`ai`；**代码默认 `ai`**（README 称默认混合） | `src/hooks/useSession.ts:44-51`、`src/lib/db.ts:326-334` |
| 风险分级 | 3 级：`none`/`hopelessness`/`suicidal` | `src/types.ts:24-27`、`src/services/crisis.ts:27-34` |
| 引擎自检 | 69 项断言、13 组 | `src/smoke_test.ts`：55 个 `t()` 调用点，其中 3 个位于循环内（INTENTS 9 项、话题 5 项、情绪变体 3 项），执行 69 项 |
| 台词白名单自检 | 12 剧本 × 18 探针 × 3 情绪 = 648 次校验 | `src/services/dialogueEngine.ts:540-568` |
| 页面数 | 11 个页面文件 | `src/pages/`（App 注册 13 条 Route，含训练双路径与兜底） |

**核验差异（文档口径与代码不一致，一律以代码为准）**

- `src/data/scenarios.ts` 12 个角色的 `nodeCount` 元数据均写 16，实际仅 W-01 为 16，另 11 个角色为 6 或 12。
- `tools/check_consistency.py:27-31` 的 TRUTH 表硬编码"规则条数 165""阻抗形态 10""视图 4"：条数 165 与九表实测一致，阻抗形态实测 6、视图实测 5 与真值不符；此前"162"的表述亦有误，已按源码更正为 165（九表）+ 6（后缀）。
- `src/data/knowledge.ts:2` 注释称"12 条伦理守则"、`:233` 小标题称"5 条伦理守则"，均为陈旧注释，数组实际为 11 条守则 + 1 条边界声明。
- README 称默认"混合模式"，代码实际默认 `ai`（全 AI）。

## E 数据库与存储现状（已确认，来自迁移 SQL 与前端代码）

| 项 | 值 |
|---|---|
| 表数量 | 7 张：`case_scripts`、`training_records`、`training_details`、`proficiency`、`achievement`、`session_record`、`user_settings` |
| 视图数量 | 5 个：`v_user_stats`（002 重建）、`v_training_heatmap`、`v_heatmap`、`v_script_progress`、`v_dimension_avg` |
| 索引数量 | 9 个（records 3 + details 1 + proficiency 1 + session 1 + 002 补充 3） |
| 触发器 | 2 个：`trg_sync_proficiency`（按日指数移动平均，新样本权重 1/3）、`trg_clear_draft_on_submit` |
| RLS 策略 | 7 张表中 6 张启用 RLS，策略全部为 `for all using (true) with check (true)`；`case_scripts` 未启用 RLS（`001_schema.sql:178-199`、`002_schema_supplements.sql:177-180`） |
| 认证 | Supabase 匿名 key（`VITE_SUPABASE_ANON_KEY`），无 Supabase Auth；昵称即身份（迁移注释自认） |
| 六维存储 | 6 个独立 int 列（非 JSON），带 0-100 check 约束 |
| 已知 schema 漂移 | `user_settings` 表无 `ai_mode` 列，而前端 upsert 与读取均含该字段（`src/lib/db.ts:326-334`、`:350-354`、`:367-386`），云端写入必失败 |
| 云端读取 | `db.ts` 的读取函数（`fetchStats`/`fetchHeatmap`/`fetchProficiency`/`fetchHistory`/`fetchDimensionAvg`/`fetchScriptProgress`/`fetchHeatmapRows`/`fetchDetails`/`loadDraft`/`loadSettings`）无任何页面 import；云端 7 表与 5 视图在运行时只写不读 |
| Edge Function | 无鉴权、无速率限制、无配额，CORS 为 `*`（`supabase/functions/wenxin-text-generation/index.ts:250`） |
| 前端存储 | localStorage 为默认权威存储；活跃键 8 个：`knock.accounts`、`knock.currentAccount`、`knock.records`、`knock.session.<account>`、`knock.settings`、`knock.debriefs`、`knock.tourDone`、`knock.nick` |
| 死键 | `knock.draft`、`knock.sessions`、`knock.heat` 仅出现在 `purgeLocal` 清理列表，无写入点 |
| 训练时长 | `durationSec` 在 `TrainingPage.tsx:227`、`:264` 两处写死 0，从未统计 |

## F 接口现状（已确认）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查：AI 配置/模型/用量/端口/uptime |
| GET | `/api/usage` | 用量快照 |
| POST | `/api/selftest` | 模型连通性自检（受限流约束） |
| POST | `/api/ai/intent` | 链路①长尾意图分类 |
| POST | `/api/ai/persona` | 链路②服务对象实时扮演 |
| POST | `/api/ai/score` | 链路③六维语义评分 |
| POST | `/api/ai/debrief` | 链路④复盘报告生成 |
| GET | `/*` | 静态资源 + SPA fallback |
| — | 共 7 个 API 端点 + 静态托管 | `server/index.mjs:112-352` |

## G 成本与性能（声明值，本轮无法实测：抽取目录无 node_modules、无可用 API key）

| 项 | 声明值 |
|---|---|
| 一次完整训练模型调用 | 3-6 次 |
| 单次调用 token | 100-600 |
| 免费档延迟 | 2-16 s（实测波动） |
| 混合模式提交阶段等待 | 5-15 s |

## H 目标侧设计基准（方案设定值，全队统一引用）

| 项 | 值 | 说明 |
|---|---|---|
| 目标并发 | 500 在线 / 100 RPS 峰值 | 一所高职院校规模（在校生 1-2 万，社工专业 300-800 人） |
| 数据规模 | 5 万学生账号、100 万训练记录/年 | 容量与索引设计基准 |
| SLO 可用性 | 99.9%（月度） | 第8章 |
| 非 AI 接口 P95 | ≤ 300 ms | 第8章 |
| AI 接口 P95 | ≤ 6 s（超时 30 s） | 第8章 |
| RPO / RTO | 15 min / 1 h | 第4章 |
| 重构周期 | 13 周 / 5 阶段 / 1 人全职 + 兼职指导 | 第9章 |
| 接口版本 | `/api/v1` | 全队 |
| 后端代码量实测 | 81 个 Python 文件 / 10,904 行（app 59 文件 8,596 行、tests 14 文件 1,394 行、scripts 5 文件 536 行、alembic 3 文件 378 行） | 交付实测值（排除 .venv/__pycache__/.pytest_cache），高于 45-60 文件 / 4,500-6,000 行的估算口径；第5/6/9章引用实测值 |

## I 核验状态

I 区 7 条待核验条目已全部完成并上移：资产计数与判定步骤见 D 区，数据库/存储口径见 E 区，工具链检查项数量见 01 文档 1.8 节（`tools/validate.py` 17 个文件级检查 + 15 条不变量；`check_consistency.py` 15 个 chk 项；其余 5 个脚本为交付物与路径级检查）。本区保留为空，后续新增待核验项在此登记。

"""从运行中的 FastAPI 应用生成《附录A API 接口清单》。

口径说明：
- 方法、路径、请求字段、响应码、鉴权要求全部读取 `app.openapi()`，不手写；
- 角色列是授权策略，OpenAPI 表达不了，故在 `ROLE_HINTS` 里集中声明；
  脚本会校验声明与真实路由完全一一对应，路由增删而声明未更新时直接失败；
- 错误码表从 `app.core.errors.ErrorCode` 反射生成。

用法：
    python scripts/gen_api_doc.py [输出路径]
默认输出到 deliverables/docs/附录A_API接口清单.md。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.errors import DEFAULT_HTTP_STATUS, ErrorCode  # noqa: E402
from app.domain.enums import Role  # noqa: E402

DEFAULT_OUTPUT = ROOT.parent / "docs" / "附录A_API接口清单.md"

# 授权策略：OpenAPI 只描述“是否需要令牌”，角色边界在这里声明并被脚本校验。
ROLE_HINTS: dict[tuple[str, str], tuple[str, str]] = {
    ("get", "/healthz"): ("公开", "无需鉴权"),
    ("get", "/readyz"): ("公开", "无需鉴权"),
    ("post", "/api/v1/auth/login"): ("公开", "按用户名密码换令牌"),
    ("post", "/api/v1/auth/refresh"): ("公开", "refresh 令牌换新令牌对"),
    ("post", "/api/v1/auth/guest"): ("公开", "游客只读体验（新增能力）"),
    ("get", "/api/v1/auth/me"): ("已登录", "任意角色"),
    ("post", "/api/v1/auth/logout"): ("已登录", "任意角色"),
    ("get", "/api/v1/scenarios"): ("公开", "案例目录"),
    ("get", "/api/v1/scenarios/{scenario_id}"): ("公开", "案例详情"),
    ("get", "/api/v1/knowledge/cards"): ("公开", "技巧卡"),
    ("get", "/api/v1/sessions"): ("已登录", "仅本人数据，游客可读"),
    ("post", "/api/v1/sessions"): ("已登录", "正式用户（游客 40301）"),
    ("get", "/api/v1/sessions/{session_id}"): ("已登录", "仅会话所有者"),
    ("post", "/api/v1/sessions/{session_id}/turns"): ("已登录", "会话所有者"),
    ("post", "/api/v1/sessions/{session_id}/stages/{stage_index}/score"): ("已登录", "会话所有者"),
    ("post", "/api/v1/sessions/{session_id}/finish"): ("已登录", "会话所有者"),
    ("post", "/api/v1/sessions/{session_id}/debrief"): ("已登录", "会话所有者"),
    ("delete", "/api/v1/sessions/{session_id}"): ("已登录", "admin"),
    ("get", "/api/v1/stats/me"): ("已登录", "仅本人数据"),
    ("get", "/api/v1/stats/heatmap"): ("已登录", "仅本人数据"),
    ("post", "/api/v1/ai/intent"): ("公开", "旧前端同源调用，按 IP 限流"),
    ("post", "/api/v1/ai/persona"): ("公开", "按 IP 限流"),
    ("post", "/api/v1/ai/score"): ("公开", "按 IP 限流"),
    ("post", "/api/v1/ai/debrief"): ("公开", "按 IP 限流"),
    ("get", "/api/health"): ("公开", "旧版，Deprecated"),
    ("get", "/api/usage"): ("公开", "旧版，Deprecated"),
    ("post", "/api/selftest"): ("公开", "旧版，Deprecated"),
    ("post", "/api/ai/intent"): ("公开", "旧版，Deprecated"),
    ("post", "/api/ai/persona"): ("公开", "旧版，Deprecated"),
    ("post", "/api/ai/score"): ("公开", "旧版，Deprecated"),
    ("post", "/api/ai/debrief"): ("公开", "旧版，Deprecated"),
    # ── 教师端（teacher / admin）────────────────────────────
    ("get", "/api/v1/teacher/learners"): ("教师", "仅名下学员"),
    ("post", "/api/v1/teacher/learners"): ("教师", "绑定学员到名下"),
    ("get", "/api/v1/teacher/stats"): ("教师", "班级聚合看板"),
    ("get", "/api/v1/teacher/learners/{owner_id}/records"): ("教师", "跨班返回空集"),
    # ── 管理端（admin）──────────────────────────────────────
    ("get", "/api/v1/admin/overview"): ("管理员", "运行概览与配额"),
    ("get", "/api/v1/admin/accounts"): ("管理员", "账号列表"),
    ("post", "/api/v1/admin/accounts"): ("管理员", "教务导入建号"),
    ("patch", "/api/v1/admin/accounts/{account_id}/active"): ("管理员", "启用 / 停用"),
    ("post", "/api/v1/admin/scenarios"): ("管理员", "新建或编辑案例"),
    ("delete", "/api/v1/admin/scenarios/{scenario_id}"): ("管理员", "下架案例"),
    ("post", "/api/v1/admin/cards"): ("管理员", "新建或编辑技巧卡"),
    ("delete", "/api/v1/admin/cards/{card_id}"): ("管理员", "删除技巧卡"),
    ("get", "/api/v1/admin/ai-logs"): ("管理员", "AI 调用审计"),
    ("get", "/api/v1/admin/rule-words"): ("管理员", "词表分组与自定义词"),
    ("post", "/api/v1/admin/rule-words"): ("管理员", "追加词条"),
    ("delete", "/api/v1/admin/rule-words/{group}/{word}"): ("管理员", "禁用词条（危机组禁止）"),
    ("delete", "/api/v1/admin/rule-words/entry/{word_id}"): ("管理员", "删除自定义词条"),
    ("get", "/api/v1/admin/script-lines"): ("管理员", "台词节点列表"),
    ("post", "/api/v1/admin/script-lines"): ("管理员", "新增台词"),
    ("patch", "/api/v1/admin/script-lines/{line_id}"): ("管理员", "编辑台词"),
    ("delete", "/api/v1/admin/script-lines/{line_id}"): ("管理员", "删除台词"),
}

TAG_ORDER = ["运维", "认证", "案例与知识卡", "训练会话", "统计", "AI 链路", "教师端", "管理端", "兼容层"]
METHOD_ORDER = ["get", "post", "delete", "put", "patch"]


def _resolve_ref(schema: dict, components: dict) -> dict:
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return components.get("schemas", {}).get(name, {})
    return schema


def _format_fields(schema: dict, components: dict) -> str:
    schema = _resolve_ref(schema, components)
    required = set(schema.get("required", []))
    parts: list[str] = []
    for name, prop in (schema.get("properties") or {}).items():
        prop = _resolve_ref(prop, components)
        kind = prop.get("type", "object")
        if kind == "array":
            item = _resolve_ref(prop.get("items", {}), components)
            kind = f"{item.get('type', 'object')}[]"
        mark = "" if name in required else "?"
        parts.append(f"{name}{mark}:{kind}")
    return "、".join(parts) if parts else "—"


def _request_fields(op: dict, components: dict) -> str:
    body = op.get("requestBody") or {}
    for media in ("application/json", "application/x-www-form-urlencoded"):
        content = (body.get("content") or {}).get(media)
        if content:
            return _format_fields(content.get("schema", {}), components)
    return "—"


def _response_codes(op: dict) -> str:
    codes = sorted(str(code) for code in (op.get("responses") or {}))
    return "、".join(codes)


def _auth_label(op: dict) -> str:
    return "Bearer" if op.get("security") else "公开"


def _collect_rows(openapi: dict) -> list[dict]:
    components = openapi.get("components", {})
    rows: list[dict] = []
    for path, item in openapi.get("paths", {}).items():
        for method, op in item.items():
            if method not in METHOD_ORDER:
                continue
            tags = op.get("tags") or ["其他"]
            auth, role = ROLE_HINTS.get((method, path), ("?", "?"))
            rows.append(
                {
                    "tag": tags[0],
                    "method": method.upper(),
                    "path": path,
                    "auth": _auth_label(op),
                    "role": role,
                    "fields": _request_fields(op, components),
                    "codes": _response_codes(op),
                    "summary": op.get("summary", ""),
                }
            )
    return rows


def _error_table() -> list[str]:
    labels = {
        ErrorCode.OK: "成功",
        ErrorCode.BAD_REQUEST: "参数校验失败",
        ErrorCode.UNAUTHORIZED: "未认证或令牌失效",
        ErrorCode.FORBIDDEN: "无权限（含越权访问他人数据）",
        ErrorCode.NOT_FOUND: "资源不存在",
        ErrorCode.CONFLICT: "状态冲突（会话已结束等）",
        ErrorCode.RATE_LIMITED: "单 IP 窗口限流",
        ErrorCode.AI_QUOTA_EXCEEDED: "AI 每日配额耗尽",
        ErrorCode.AI_UNAVAILABLE: "AI 能力不可用",
        ErrorCode.INTERNAL: "服务内部错误",
    }
    lines = ["| code | HTTP | 含义 |", "| --- | --- | --- |"]
    for code in ErrorCode:
        lines.append(f"| {int(code)} | {DEFAULT_HTTP_STATUS.get(code, 200)} | {labels.get(code, '')} |")
    return lines


def render(openapi: dict) -> str:
    rows = _collect_rows(openapi)
    by_tag: dict[str, list[dict]] = {}
    for row in rows:
        by_tag.setdefault(row["tag"], []).append(row)

    unknown = sorted(set(by_tag) - set(TAG_ORDER))
    if unknown:
        raise SystemExit(f"新增分组未排序：{unknown}")
    declared = {(m, p) for m, p in ROLE_HINTS}
    actual = {(row["method"].lower(), row["path"]) for row in rows}
    if declared != actual:
        missing = sorted(actual - declared)
        stale = sorted(declared - actual)
        raise SystemExit(f"角色声明与真实路由不一致，缺失={missing} 多余={stale}")

    lines = [
        "# 附录A API 接口清单",
        "",
        "本清单由 `deliverables/backend/scripts/gen_api_doc.py` 读取运行中应用的 "
        "`app.openapi()` 自动生成，方法、路径、请求字段与响应码均取自 OpenAPI 文档，"
        "角色列对应第 5 章的 RBAC 矩阵。",
        "",
        f"接口总数：{len(rows)} 条；统一前缀 `/api/v1`，健康检查与指标端点位于根路径。",
        "",
        "## A.1 通用响应包与错误码",
        "",
        "除旧版兼容接口外，所有接口返回统一响应包 `{code, message, data, request_id}`；"
        "`code=0` 表示成功，非 0 时 `data` 为 null，HTTP 状态码与错误码一一对应。",
        "",
        "**表 A-1 统一错误码**",
        "",
        *_error_table(),
        "",
        "## A.2 接口明细",
        "",
    ]
    index = 1
    for tag in TAG_ORDER:
        items = by_tag.get(tag)
        if not items:
            continue
        lines += [f"### {tag}", "", f"**表 A-{index + 1} {tag}接口**", ""]
        index += 1
        lines += ["| 方法 | 路径 | 鉴权 | 角色约束 | 请求字段 | 响应码 | 说明 |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for row in sorted(items, key=lambda r: (METHOD_ORDER.index(r["method"].lower()), r["path"])):
            lines.append(
                "| {method} | `{path}` | {auth} | {role} | {fields} | {codes} | {summary} |".format(
                    **row
                )
            )
        lines.append("")
    lines += [
        "## A.3 鉴权与限流约定",
        "",
        "- `Authorization: Bearer <access_token>`：access 令牌有效期 30 分钟，"
        "refresh 令牌 7 天且一次性轮换（旧 refresh 立即撤销）。",
        "- 游客令牌 24 小时有效，仅可读取案例、知识卡与本人会话，写操作返回 40301。",
        "- `/api/v1/ai/*` 与旧版 `/api/ai/*` 按单 IP 每分钟 20 次限流，超限返回 42901；"
        "AI 每日 800 次配额耗尽返回 42902。",
        "- 旧版接口响应附带 `Deprecation`、`Sunset`、`Link` 与 `X-Knock-Api: legacy` 头，"
        "响应体保持旧形状，便于前端灰度切换。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    from app.main import app

    text = render(app.openapi())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"wrote {output} ({len(text)} chars)")


if __name__ == "__main__":
    main()

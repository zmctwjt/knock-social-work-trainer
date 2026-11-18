"""统一响应包构造。

所有对外 JSON 都形如 `{code, message, data, request_id}`：
- `code=0` 成功；非 0 见 `app.core.errors.ErrorCode`；
- `request_id` 由中间件生成并回写 `X-Request-ID` 响应头，便于跨日志串联；
- 分页统一用 `{items, total, page?, page_size?}` 放在 `data` 内。
"""

from __future__ import annotations

from typing import Any

from app.core.context import get_request_id


def envelope(
    data: Any = None,
    message: str = "ok",
    code: int = 0,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": get_request_id(),
    }


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return envelope(data=data, message=message, code=0)


def page(items: list[Any], total: int, page_no: int = 1, page_size: int = 20) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page_no,
        "page_size": page_size,
    }

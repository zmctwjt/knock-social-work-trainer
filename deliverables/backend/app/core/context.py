"""请求级上下文（contextvars）。

中间件在请求入口写入 `request_id` 与脱敏后的 `user_id_hash`，
日志、审计、错误响应统一从这里取，避免层层透传。
"""

from __future__ import annotations

import contextvars

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
user_id_hash_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id_hash", default="anonymous"
)


def get_request_id() -> str:
    return request_id_ctx.get()


def set_request_id(value: str) -> contextvars.Token[str]:
    return request_id_ctx.set(value)


def reset_request_id(token: contextvars.Token[str]) -> None:
    request_id_ctx.reset(token)


def get_user_id_hash() -> str:
    return user_id_hash_ctx.get()


def set_user_id_hash(value: str) -> contextvars.Token[str]:
    return user_id_hash_ctx.set(value)


def reset_user_id_hash(token: contextvars.Token[str]) -> None:
    user_id_hash_ctx.reset(token)

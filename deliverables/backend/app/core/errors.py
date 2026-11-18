"""统一错误码与异常处理。

响应包固定为 `{code, message, data, request_id}`；`code=0` 表示成功。
错误码表是前后端契约的一部分，新增错误码必须同步更新第 5 章与附录 A。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id


class ErrorCode(IntEnum):
    """业务错误码。"""

    OK = 0
    BAD_REQUEST = 40001
    UNAUTHORIZED = 40101
    FORBIDDEN = 40301
    NOT_FOUND = 40401
    CONFLICT = 40901
    RATE_LIMITED = 42901
    AI_QUOTA_EXCEEDED = 42902
    AI_UNAVAILABLE = 50301
    INTERNAL = 50001


#: 错误码 → 默认 HTTP 状态码
DEFAULT_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.OK: 200,
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.AI_QUOTA_EXCEEDED: 429,
    ErrorCode.AI_UNAVAILABLE: 503,
    ErrorCode.INTERNAL: 500,
}


class AppError(Exception):
    """业务异常。由异常处理器统一翻译为响应包。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Any = None,
        http_status: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.http_status = http_status or DEFAULT_HTTP_STATUS.get(code, 500)
        self.headers = headers or {}

    # ── 常用构造器 ──
    @classmethod
    def bad_request(cls, message: str, details: Any = None) -> "AppError":
        return cls(ErrorCode.BAD_REQUEST, message, details=details)

    @classmethod
    def unauthorized(cls, message: str = "未认证或登录已过期") -> "AppError":
        return cls(ErrorCode.UNAUTHORIZED, message)

    @classmethod
    def forbidden(cls, message: str = "无权访问该资源") -> "AppError":
        return cls(ErrorCode.FORBIDDEN, message)

    @classmethod
    def not_found(cls, message: str = "资源不存在") -> "AppError":
        return cls(ErrorCode.NOT_FOUND, message)

    @classmethod
    def conflict(cls, message: str = "当前状态不允许该操作") -> "AppError":
        return cls(ErrorCode.CONFLICT, message)

    @classmethod
    def rate_limited(cls, message: str = "请求过于频繁，请稍候再试") -> "AppError":
        return cls(ErrorCode.RATE_LIMITED, message)

    @classmethod
    def quota_exceeded(cls, message: str = "已达当日 AI 调用上限") -> "AppError":
        return cls(ErrorCode.AI_QUOTA_EXCEEDED, message)

    @classmethod
    def ai_unavailable(cls, message: str = "AI 服务暂不可用，已切换规则模式") -> "AppError":
        return cls(ErrorCode.AI_UNAVAILABLE, message)


def error_body(code: ErrorCode | int, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "code": int(code),
        "message": message,
        "data": details,
        "request_id": get_request_id(),
    }


def _json_error(
    code: ErrorCode,
    message: str,
    *,
    http_status: int,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        content=error_body(code, message, details),
        status_code=http_status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


def install_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器（顺序无关，星标本就是按类型精确匹配）。"""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _json_error(
            exc.code,
            exc.message,
            http_status=exc.http_status,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for item in exc.errors()[:5]:
            loc = ".".join(str(x) for x in item.get("loc", []) if x != "body")
            errors.append({"field": loc, "reason": item.get("msg", "invalid")})
        return _json_error(
            ErrorCode.BAD_REQUEST,
            "请求参数不合法",
            http_status=400,
            details=errors or None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapping = {
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            429: ErrorCode.RATE_LIMITED,
        }
        code = mapping.get(exc.status_code, ErrorCode.BAD_REQUEST)
        return _json_error(
            code,
            str(exc.detail) if exc.detail else code.name,
            http_status=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        # 兜底：绝不把堆栈或密钥带进响应体
        return _json_error(
            ErrorCode.INTERNAL,
            "服务器内部错误，请稍后重试或联系管理员",
            http_status=500,
        )


class StartupConfigError(RuntimeError):
    """生产环境配置不达标时抛出，用于拒绝启动。

    不在 `AppError` 体系内：它不是一次请求的错误，而是进程级致命问题，
    必须在监听端口之前就让进程退出，避免"带病上线"。
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        detail = "；".join(self.problems)
        super().__init__(f"生产环境配置未达标，拒绝启动：{detail}")

"""中间件链：请求标识、访问日志、体积限制、安全响应头。

执行顺序（外 → 内）：CORS → TrustedHost → RequestContext → BodyLimit → 路由。
- `RequestContextMiddleware` 生成/透传 `X-Request-ID`，把 request_id 与
  耗时写进 structlog 上下文，并回写响应头——这是跨日志排障的主键；
- `BodyLimitMiddleware` 复刻旧 Node 服务 512KB 的限制（超出 413），
  但只检查 Content-Length，不做流式缓冲，避免把大文件读进内存；
- 安全响应头默认全站生效，接口响应额外 `Cache-Control: no-store`。
"""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.context import reset_request_id, set_request_id
from app.core.errors import ErrorCode, error_body
from app.core.metrics import observe_http

logger = structlog.get_logger("http")

#: 所有响应都下发的通用头（与内容类型无关）
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-XSS-Protection": "0",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}

#: 接口响应用的 CSP：不渲染页面，收到最严
CSP_API = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

#: 前端页面用的 CSP：需要允许自身的 JS/CSS 与同源接口请求。
#:
#: 关键约束是不能用 `'unsafe-inline'` 之外还开 `default-src 'none'`——
#: 单端口部署时后端同时托管 HTML，若沿用接口那套 `default-src 'none'`，
#: 页面自己的 `<script src="/assets/*.js">` 会被拦掉，表现为"白屏 + CSP 报错"。
#: 这里只放行同源资源，仍禁止外域脚本与内联事件处理器。
CSP_WEB = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
    "object-src 'none'"
)

#: 静态资源（js/css/图片/字体）本身不需要 CSP，套上只会干扰子资源加载
_CSP_SKIP_PREFIXES = ("/assets/",)


def pick_csp(path: str, content_type: str) -> str | None:
    """按请求路径与响应类型选 CSP。

    - 接口（/api、/healthz 等）与白名单外路径 → 最严 `CSP_API`
    - 前端 HTML 页面 → `CSP_WEB`（放行同源脚本样式）
    - 静态子资源 → 不下发（浏览器只按文档的 CSP 执行）
    """
    if any(path.startswith(prefix) for prefix in _CSP_SKIP_PREFIXES):
        return None
    if "text/html" in content_type:
        return CSP_WEB
    return CSP_API

#: 仅 HTTPS 场景下发（开发期 HTTP 加 HSTS 会让浏览器记住 localhost，反而影响调试）
HSTS_HEADER = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        token = set_request_id(request_id)
        started = time.perf_counter()
        status = 500

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            for key, value in SECURITY_HEADERS.items():
                response.headers.setdefault(key, value)
            csp = pick_csp(request.url.path, response.headers.get("content-type", ""))
            if csp:
                response.headers.setdefault("Content-Security-Policy", csp)
            # 生产（等同 HTTPS）才加 HSTS；开发环境加会让浏览器强制升级本地域名
            if self.settings.is_prod:
                for key, value in HSTS_HEADER.items():
                    response.headers.setdefault(key, value)
            if request.url.path.startswith(self.settings.api_v1_prefix) or request.url.path.startswith("/api/"):
                response.headers.setdefault("Cache-Control", "no-store")
            return response
        except Exception:
            status = 500
            raise
        finally:
            duration = (time.perf_counter() - started) * 1000
            route = request.scope.get("route")
            path_label = getattr(route, "path", request.url.path)
            observe_http(request.method, path_label, status, duration / 1000)
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                route=path_label,
                status=status,
                duration_ms=round(duration, 2),
                client_ip=get_client_ip(request)[:64],
            )
            structlog.contextvars.clear_contextvars()
            reset_request_id(token)


class BodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limit_bytes: int) -> None:
        super().__init__(app)
        self.limit_bytes = limit_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw = request.headers.get("content-length")
        if raw is not None:
            try:
                length = int(raw)
            except ValueError:
                length = 0
            if length > self.limit_bytes:
                return JSONResponse(
                    status_code=413,
                    content=error_body(
                        ErrorCode.BAD_REQUEST,
                        f"请求体超过上限（{self.limit_bytes // 1024}KB）",
                        {"limit_bytes": self.limit_bytes},
                    ),
                    headers={"X-Request-ID": request.headers.get("x-request-id", "")},
                )
        return await call_next(request)


def get_client_ip(request: Request) -> str:
    """与旧 Node 实现保持一致：取 `X-Forwarded-For` 首段，否则用连接地址。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    client = request.client
    return client.host if client else "unknown"

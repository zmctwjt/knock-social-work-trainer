"""API 层依赖：从 `app.state` 取基础设施，并封装限流依赖。

`app.state` 里的对象全部由 `app.main` 的 lifespan 创建，接口层只读不建，
这样测试可以用 `build_container()` 换掉任意一个部件（DB、Redis、AI 网关）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.deps import SettingsDep
from app.core.errors import AppError, ErrorCode
from app.core.middleware import get_client_ip
from app.core.ratelimit import RateLimiter
from app.infra.cache import AICache
from app.infra.redis import KVStore
from app.services.ai_gateway import AIGateway
from app.services.llm.quota import DailyQuota
from app.services.llm.usage import UsageTracker


def get_gateway(request: Request) -> AIGateway:
    return request.app.state.ai_gateway


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


def get_store(request: Request) -> KVStore:
    return request.app.state.store


def get_cache(request: Request) -> AICache:
    return request.app.state.cache


def get_quota(request: Request) -> DailyQuota:
    return request.app.state.quota


def get_usage(request: Request) -> UsageTracker:
    return request.app.state.usage


GatewayDep = Annotated[AIGateway, Depends(get_gateway)]
LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]
UsageDep = Annotated[UsageTracker, Depends(get_usage)]
QuotaDep = Annotated[DailyQuota, Depends(get_quota)]


async def _enforce(scope: str, request: Request, settings, limiter: RateLimiter) -> None:
    if not settings.rate_limit_enabled:
        return
    identity = get_client_ip(request)
    allowed, remaining = await limiter.hit(scope, identity)
    if not allowed:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "请求过于频繁，请稍后再试",
            details={"scope": scope, "window_sec": settings.rate_limit_window_sec},
            headers={"Retry-After": str(settings.rate_limit_window_sec)},
        )


async def ai_rate_limit(request: Request, settings: SettingsDep, limiter: LimiterDep) -> None:
    """AI 链路限流：与旧 Node 版一致，单 IP 20 次/分钟（跨进程靠 Redis）。"""
    await _enforce("ai", request, settings, limiter)


async def auth_rate_limit(request: Request, settings: SettingsDep, limiter: LimiterDep) -> None:
    """认证入口限流：防撞库，窗口与阈值复用同一套配置。"""
    await _enforce("auth", request, settings, limiter)

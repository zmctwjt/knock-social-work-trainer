"""/api/v1 路由聚合。

每个业务域一个模块，聚合层只做 `include_router`，不写业务逻辑——
这样 OpenAPI 的 `tags` 与文件的对应关系保持一目了然，也方便按域做权限收口。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import ai, auth, roles, scenarios, sessions, stats

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(scenarios.router)
api_router.include_router(sessions.router)
api_router.include_router(stats.router)
api_router.include_router(ai.router)
api_router.include_router(roles.teacher_router)
api_router.include_router(roles.admin_router)

__all__ = ["api_router"]

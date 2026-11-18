"""请求级数据库会话依赖。

与 `Database.session()` 的差别：这里的会话在请求结束时由 FastAPI 关闭，
提交动作交给服务层显式 `await session.commit()`（读接口不产生无谓的事务）。
"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db import Database


def get_database(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "db", None)
    if database is None:  # pragma: no cover - 只会在装配错误时发生
        raise RuntimeError("app.state.db 未初始化")
    return database


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database = get_database(request)
    if database.session_factory is None:  # pragma: no cover
        raise RuntimeError("数据库未就绪")
    async with database.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

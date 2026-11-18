"""数据库引擎与会话工厂（SQLAlchemy 2.0 async）。

三种用途共用一套代码：
- 生产 / 本机部署：`mysql+aiomysql://`（MySQL 8.0），连接池 10 + 溢出 20，
  `pool_pre_ping` 防掉线，`pool_recycle` 规避 wait_timeout；
- 兼容：`postgresql+asyncpg://` 仍可工作（仅方言差异由 SQLAlchemy 处理）；
- 测试：`sqlite+aiosqlite://`（内存库）自动改 `StaticPool`，否则每个连接
  都会拿到一个新的空库，测试会诡异失败。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import Settings


def _is_memory_sqlite(url: str) -> bool:
    return url.startswith("sqlite") and (
        ":memory:" in url or url in ("sqlite+aiosqlite://", "sqlite://")
    )


class Database:
    """引擎生命周期与健康检查的唯一持有者。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self._lock = asyncio.Lock()

    # ── 生命周期 ──
    async def connect(self) -> None:
        async with self._lock:
            if self.engine is not None:
                return
            self.engine = self._create_engine()
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False,
            )
            if self.settings.auto_create_schema:
                from app.domain.models import Base

                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

    async def disconnect(self) -> None:
        async with self._lock:
            if self.engine is not None:
                await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    def _create_engine(self) -> AsyncEngine:
        settings = self.settings
        url = settings.database_url
        kwargs: dict[str, object] = {"echo": settings.db_echo, "future": True}

        if url.startswith("sqlite"):
            if _is_memory_sqlite(url):
                kwargs["poolclass"] = StaticPool
                kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_pre_ping=True,
                pool_recycle=1_800,
            )
        return create_async_engine(url, **kwargs)

    # ── 使用 ──
    def factory(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("Database 尚未 connect()，请在 lifespan 中初始化")
        return self.session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """自动提交/回滚的会话上下文；业务代码不需要手写 commit。"""
        if self.session_factory is None:
            raise RuntimeError("Database 尚未 connect()")
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """就绪探针用：执行一次最轻量的查询。"""
        if self.engine is None:
            return False
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    @property
    def dialect(self) -> str:
        return self.settings.db_dialect

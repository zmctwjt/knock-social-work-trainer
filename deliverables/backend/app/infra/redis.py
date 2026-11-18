"""键值存储抽象：生产用 Redis，未配置或测试时退回进程内实现。

为什么保留两套实现：
- 配额（800 次/日）与限流（20 次/分/IP）必须跨进程精确，只有 Redis 能保证；
- 但单机评测、CI、`pytest` 不应被迫拉起 Redis，否则"能跑起来"就成了一句空话。
  因此 `REDIS_URL` 留空时自动降级为内存实现，并在日志与 /readyz 里明确标注。
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol

from app.core.config import Settings


class KVStore(Protocol):
    """原子操作的最小集合。`incr` 的 TTL 只在键首次创建时设置。"""

    backend: str

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class MemoryStore:
    """进程内实现（单进程语义，多 worker 下各算各的）。"""

    backend = "memory"

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._expires: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _purge(self, key: str) -> None:
        deadline = self._expires.get(key)
        if deadline is not None and deadline <= time.monotonic():
            self._data.pop(key, None)
            self._expires.pop(key, None)

    async def get(self, key: str) -> str | None:
        async with self._lock:
            self._purge(key)
            return self._data.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        async with self._lock:
            self._data[key] = value
            if ttl is not None:
                self._expires[key] = time.monotonic() + ttl
            else:
                self._expires.pop(key, None)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self._expires.pop(key, None)

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        async with self._lock:
            self._purge(key)
            current = int(self._data.get(key, "0") or 0) + amount
            self._data[key] = str(current)
            if key not in self._expires and ttl is not None:
                self._expires[key] = time.monotonic() + ttl
            return current

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._data.clear()
        self._expires.clear()

    def reset(self) -> None:
        """测试辅助：清空全部键。"""
        self._data.clear()
        self._expires.clear()


class RedisStore:
    """Redis 实现。连接懒加载，`ping` 失败由调用方决定是否降级。"""

    backend = "redis"

    def __init__(self, url: str) -> None:
        self.url = url
        self._client = None
        self._lock = asyncio.Lock()

    async def _client_or_connect(self):
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    from redis.asyncio import Redis

                    self._client = Redis.from_url(
                        self.url,
                        encoding="utf-8",
                        decode_responses=True,
                        socket_connect_timeout=2,
                        socket_timeout=2,
                        health_check_interval=30,
                    )
        return self._client

    async def get(self, key: str) -> str | None:
        client = await self._client_or_connect()
        value = await client.get(key)
        return value if value is None else str(value)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        client = await self._client_or_connect()
        if ttl is None:
            await client.set(key, value)
        else:
            await client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        client = await self._client_or_connect()
        await client.delete(key)

    async def incr(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        client = await self._client_or_connect()
        value = int(await client.incrby(key, amount))
        if value == amount and ttl is not None:
            await client.expire(key, ttl)
        return value

    async def ping(self) -> bool:
        try:
            client = await self._client_or_connect()
            return bool(await client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None


def create_store(settings: Settings) -> KVStore:
    """按配置创建存储：有 REDIS_URL 用 Redis，否则内存。"""
    if settings.redis_url.strip():
        return RedisStore(settings.redis_url.strip())
    return MemoryStore()

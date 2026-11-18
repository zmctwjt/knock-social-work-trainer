"""AI 结果缓存（L1 进程内 LRU + L2 Redis）。

键必须包含三样东西，缺一就会出现"换了提示词还在吃旧缓存"的事故：
`purpose + prompt_version + model + sha256(规范化输入)`。

容量策略：L1 严格 300 条 LRU；L2 由 Redis `allkeys-lru` 兜底，
因为跨进程精确统计容量需要额外的一致性协议，收益远低于复杂度。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from app.infra.redis import KVStore

CACHE_KEY_PREFIX = "knock:ai:cache:"


def build_cache_key(
    purpose: str,
    prompt_version: str,
    model: str,
    payload: dict[str, Any],
) -> str:
    """规范化输入后取哈希：字段顺序不同但语义相同应命中同一条缓存。"""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{CACHE_KEY_PREFIX}{purpose}:{prompt_version}:{model}:{digest}"


class TTLCache:
    """进程内 TTL + LRU。命中时把键移到队尾，淘汰队首。"""

    def __init__(self, max_size: int = 300, ttl_sec: int = 600) -> None:
        self.max_size = max(1, max_size)
        self.ttl_sec = max(1, ttl_sec)
        self._data: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> str | None:
        async with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            value, expires_at = item
            if expires_at <= time.monotonic():
                self._data.pop(key, None)
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        async with self._lock:
            self._data[key] = (value, time.monotonic() + (ttl or self.ttl_sec))
            self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class AICache:
    """两级缓存门面。L2 故障不得影响主流程——读写都用 try/except 吞掉。"""

    def __init__(self, store: KVStore, ttl_sec: int = 600, max_size: int = 300) -> None:
        self.store = store
        self.ttl_sec = ttl_sec
        self.l1 = TTLCache(max_size=max_size, ttl_sec=ttl_sec)
        self.l2_hits = 0

    async def get(self, key: str) -> str | None:
        hit = await self.l1.get(key)
        if hit is not None:
            return hit
        try:
            value = await self.store.get(key)
        except Exception:
            return None
        if value is None:
            return None
        self.l2_hits += 1
        await self.l1.set(key, value, self.ttl_sec)
        return value

    async def set(self, key: str, value: str) -> None:
        await self.l1.set(key, value, self.ttl_sec)
        try:
            await self.store.set(key, value, ttl=self.ttl_sec)
        except Exception:
            pass

    async def clear(self) -> None:
        await self.l1.clear()

    @property
    def stats(self) -> dict[str, int]:
        return {
            "l1_size": len(self.l1),
            "l1_hits": self.l1.hits,
            "l1_misses": self.l1.misses,
            "l2_hits": self.l2_hits,
        }

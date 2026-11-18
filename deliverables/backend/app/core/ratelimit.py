"""接口限流：固定窗口计数（默认 20 次 / 60 秒 / IP）。

为什么是固定窗口而不是令牌桶：旧 Node 服务的语义就是"每分钟 20 次"，
固定窗口与之等价且只需一次 `INCR`，在 Redis 上不存在竞态；
代价是窗口边界可能瞬时放行 2 倍流量，对"防误点"这个目标可以接受。
"""

from __future__ import annotations

import time

from app.core.config import Settings
from app.infra.redis import KVStore

RATE_LIMIT_PREFIX = "knock:rl:"


class RateLimiter:
    def __init__(self, store: KVStore, settings: Settings) -> None:
        self.store = store
        self.limit = max(1, settings.glm_rpm_per_ip)
        self.window = max(1, settings.rate_limit_window_sec)
        self.enabled = settings.rate_limit_enabled

    def _bucket(self) -> int:
        return int(time.time() // self.window)

    def _key(self, scope: str, identity: str) -> str:
        return f"{RATE_LIMIT_PREFIX}{scope}:{identity}:{self._bucket()}"

    async def hit(self, scope: str, identity: str) -> tuple[bool, int]:
        """记一次并返回 `(是否放行, 剩余次数)`。存储故障时放行（可用性优先）。"""
        if not self.enabled:
            return True, self.limit
        try:
            count = await self.store.incr(self._key(scope, identity), 1, ttl=self.window)
        except Exception:
            return True, self.limit
        return count <= self.limit, max(0, self.limit - count)

    async def remaining(self, scope: str, identity: str) -> int:
        if not self.enabled:
            return self.limit
        try:
            raw = await self.store.get(self._key(scope, identity))
        except Exception:
            return self.limit
        used = int(raw) if raw is not None else 0
        return max(0, self.limit - used)

    async def reset(self, scope: str, identity: str) -> None:
        """测试辅助：清掉当前窗口计数。"""
        try:
            await self.store.delete(self._key(scope, identity))
        except Exception:
            pass

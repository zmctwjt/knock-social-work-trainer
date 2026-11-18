"""AI 用量计数器（进程内）。

用途有两个：
1. `/api/usage`（旧接口兼容）与 `/healthz` 的 `usage` 字段需要与旧 Node 版
   同形状的数字；
2. 本地排障时能立刻回答"这一小时到底调了多少次、降级了多少次"。

注意：进程内计数在多 worker 下是各算各的，精确配额一律以 Redis 为准。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class UsageCounters:
    calls: int = 0
    ok: int = 0
    failed: int = 0
    degraded: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    by_function: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "ok": self.ok,
            "failed": self.failed,
            "degraded": self.degraded,
            "cacheHits": self.cache_hits,
            "byFunction": dict(self.by_function),
            "tokensIn": self.tokens_in,
            "tokensOut": self.tokens_out,
        }


class UsageTracker:
    def __init__(self) -> None:
        self._counters = UsageCounters()
        self._lock = asyncio.Lock()

    async def record_call(
        self,
        purpose: str,
        *,
        ok: bool,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        async with self._lock:
            counters = self._counters
            counters.calls += 1
            counters.by_function[purpose] = counters.by_function.get(purpose, 0) + 1
            if ok:
                counters.ok += 1
                counters.tokens_in += tokens_in
                counters.tokens_out += tokens_out
            else:
                counters.failed += 1

    async def record_degraded(self) -> None:
        async with self._lock:
            self._counters.degraded += 1

    async def record_cache_hit(self) -> None:
        async with self._lock:
            self._counters.cache_hits += 1

    async def snapshot(self) -> dict[str, object]:
        async with self._lock:
            return self._counters.snapshot()

    def reset(self) -> None:
        self._counters = UsageCounters()

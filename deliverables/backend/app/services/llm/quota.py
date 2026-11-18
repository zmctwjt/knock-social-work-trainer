"""每日 AI 配额（跨进程精确，默认 800 次/日）。

计数键按东八区日期切分：`knock:ai:quota:YYYYMMDD`。
用 Redis `INCR` 的原因是"先查后写"在并发下一定超发；
`INCR` 的返回值就是已用次数，天然原子。
键的 TTL 给两天，避免跨日残留把第二天的配额吃掉。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.errors import AppError
from app.core.metrics import AI_QUOTA_USED
from app.infra.redis import KVStore

QUOTA_PREFIX = "knock:ai:quota:"
QUOTA_TTL_SEC = 2 * 86_400 + 3_600
BEIJING = timezone(timedelta(hours=8))


def quota_date(now: datetime | None = None) -> str:
    moment = now or datetime.now(BEIJING)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING)
    return moment.astimezone(BEIJING).strftime("%Y%m%d")


class DailyQuota:
    def __init__(self, store: KVStore, daily_cap: int) -> None:
        self.store = store
        self.daily_cap = max(1, daily_cap)

    def key(self, now: datetime | None = None) -> str:
        return f"{QUOTA_PREFIX}{quota_date(now)}"

    async def used(self) -> int:
        try:
            raw = await self.store.get(self.key())
        except Exception:
            return 0
        try:
            return int(raw or 0)
        except ValueError:
            return 0

    async def remaining(self) -> int:
        return max(0, self.daily_cap - await self.used())

    async def consume(self) -> int:
        """占用一次配额；超限抛 42902。返回占用后的已用次数。"""
        try:
            count = await self.store.incr(self.key(), 1, ttl=QUOTA_TTL_SEC)
        except Exception:
            # 存储故障时放行：宁可短暂少计，也不要让整个 AI 链路不可用
            return -1
        AI_QUOTA_USED.set(float(count))
        if count > self.daily_cap:
            raise AppError.quota_exceeded(
                f"已达当日 AI 调用上限（{self.daily_cap} 次），请明天再试或使用规则模式"
            )
        return count

    async def snapshot(self) -> dict[str, int]:
        used = await self.used()
        return {
            "used": used,
            "daily_cap": self.daily_cap,
            "remaining": max(0, self.daily_cap - used),
        }

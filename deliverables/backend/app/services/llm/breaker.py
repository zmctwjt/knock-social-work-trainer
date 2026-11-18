"""熔断器（按模型独立计数）。

状态机：
    CLOSED --失败率>50% 且样本≥10--> OPEN --等待 30s--> HALF_OPEN
    HALF_OPEN --探测成功--> CLOSED
    HALF_OPEN --探测失败--> OPEN（重新计时）

为什么阈值是 50% / 10 个样本：单次抖动不足以判死一个模型，
但连续 10 次里坏掉 6 次就说明上游确实有问题；30 秒的打开时长
等于一次人工排障的起步时间，也避免对上游造成持续压力。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass

from app.core.metrics import BREAKER_OPEN_COUNT, BREAKER_STATE

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

STATE_VALUE = {CLOSED: 0, HALF_OPEN: 1, OPEN: 2}


@dataclass
class BreakerSnapshot:
    model: str
    state: str
    samples: int
    failures: int
    failure_rate: float
    opened_until: float


class CircuitBreaker:
    def __init__(
        self,
        model: str,
        *,
        failure_threshold: float = 0.5,
        min_samples: int = 10,
        open_sec: float = 30.0,
        window: int = 20,
    ) -> None:
        self.model = model
        self.failure_threshold = failure_threshold
        self.min_samples = min_samples
        self.open_sec = open_sec
        self.window = window
        self.state = CLOSED
        self._samples: deque[bool] = deque(maxlen=window)
        self._opened_at: float = 0.0
        self._half_open_probe = False
        self._lock = asyncio.Lock()
        self._sync_metric()

    # ── 只读视图 ──
    @property
    def failure_rate(self) -> float:
        if not self._samples:
            return 0.0
        failures = sum(1 for ok in self._samples if not ok)
        return failures / len(self._samples)

    @property
    def failures(self) -> int:
        return sum(1 for ok in self._samples if not ok)

    def snapshot(self) -> BreakerSnapshot:
        return BreakerSnapshot(
            model=self.model,
            state=self.state,
            samples=len(self._samples),
            failures=self.failures,
            failure_rate=round(self.failure_rate, 3),
            opened_until=round(self._opened_at + self.open_sec, 3),
        )

    # ── 判定 ──
    async def allow(self) -> bool:
        """是否允许本次调用通过。HALF_OPEN 时只放行一个探测请求。"""
        async with self._lock:
            if self.state == CLOSED:
                return True
            if self.state == OPEN:
                if time.monotonic() - self._opened_at >= self.open_sec:
                    self.state = HALF_OPEN
                    self._half_open_probe = False
                    self._sync_metric()
                else:
                    return False
            if self.state == HALF_OPEN:
                if self._half_open_probe:
                    return False
                self._half_open_probe = True
                return True
            return False

    async def record(self, success: bool) -> None:
        async with self._lock:
            if self.state == HALF_OPEN:
                if success:
                    self._samples.clear()
                    self.state = CLOSED
                else:
                    self._trip()
                self._half_open_probe = False
                self._sync_metric()
                return

            self._samples.append(success)
            if (
                self.state == CLOSED
                and len(self._samples) >= self.min_samples
                and self.failure_rate > self.failure_threshold
            ):
                self._trip()
                self._sync_metric()

    def _trip(self) -> None:
        if self.state != OPEN:
            BREAKER_OPEN_COUNT.labels(self.model).inc()
        self.state = OPEN
        self._opened_at = time.monotonic()

    def _sync_metric(self) -> None:
        BREAKER_STATE.labels(self.model).set(STATE_VALUE.get(self.state, 0))

    def reset(self) -> None:
        """测试辅助：强制回到 CLOSED 并清空样本。"""
        self.state = CLOSED
        self._samples.clear()
        self._opened_at = 0.0
        self._half_open_probe = False
        self._sync_metric()


def build_breakers(models: list[str], *, failure_threshold: float, min_samples: int, open_sec: float) -> dict[str, CircuitBreaker]:
    return {
        model: CircuitBreaker(
            model,
            failure_threshold=failure_threshold,
            min_samples=min_samples,
            open_sec=open_sec,
        )
        for model in models
    }

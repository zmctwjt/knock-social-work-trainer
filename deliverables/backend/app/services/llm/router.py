"""模型链路由：主模型 2 次尝试、降级模型各 1 次，仅 429/5xx/超时降级。

与旧实现的差异只有一处：把"主模型 2 次、降级 1 次"从硬编码改成
`GLM_MAX_RETRIES` 驱动（默认 1，即主模型共 2 次尝试），行为保持不变。

关键约定：**非可重试错误立即中止整条链**。原因是鉴权失败、参数错误、
空回复这类问题换模型也不会好，只会把一次失败变成三次计费。
"""

from __future__ import annotations

import asyncio
import random
import time

from app.core.config import Settings
from app.core.metrics import AI_CALLS, AI_LATENCY
from app.services.llm.base import (
    AllModelsFailed,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
)
from app.services.llm.breaker import CircuitBreaker, build_breakers


class ModelRouter:
    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider,
        *,
        backoff_base: float = 0.7,
        sleeper=asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.chain = settings.model_chain
        self.backoff_base = backoff_base
        self._sleep = sleeper
        self.breakers: dict[str, CircuitBreaker] = build_breakers(
            self.chain,
            failure_threshold=settings.glm_breaker_failure_threshold,
            min_samples=settings.glm_breaker_min_samples,
            open_sec=settings.glm_breaker_open_sec,
        )

    def attempts_for(self, model: str) -> int:
        """主模型允许 1 次重试；降级模型只打一枪。"""
        if model == self.chain[0]:
            return max(1, self.settings.glm_max_retries + 1)
        return 1

    async def complete(
        self,
        *,
        purpose: str,
        system: str,
        user: str,
        json_mode: bool = True,
        max_tokens: int = 400,
        temperature: float = 0.3,
    ) -> LLMResponse:
        last_reason = "no_model"
        last_detail = ""

        for model in self.chain:
            breaker = self.breakers[model]
            if not await breaker.allow():
                last_reason = "breaker_open"
                last_detail = f"{model} 熔断中"
                continue

            request = LLMRequest(
                model=model,
                messages=[
                    # 用 dict 兼容不同供应商的角色字段
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
                timeout_ms=self.settings.glm_timeout_ms,
                purpose=purpose,
            )

            for attempt in range(self.attempts_for(model)):
                started = time.perf_counter()
                try:
                    response = await self.provider.complete(request)
                except ProviderError as exc:
                    elapsed = time.perf_counter() - started
                    AI_LATENCY.labels(model).observe(elapsed)
                    AI_CALLS.labels(self.provider.name, model, exc.reason).inc()
                    await breaker.record(False)
                    last_reason, last_detail = exc.reason, exc.detail
                    if not exc.retryable:
                        raise AllModelsFailed(exc.reason, exc.detail) from exc
                    if attempt + 1 >= self.attempts_for(model):
                        break
                    await self._backoff(attempt)
                    continue

                elapsed = time.perf_counter() - started
                AI_LATENCY.labels(model).observe(elapsed)
                AI_CALLS.labels(self.provider.name, model, "ok").inc()
                await breaker.record(True)
                return response

        raise AllModelsFailed(last_reason, last_detail)

    async def _backoff(self, attempt: int) -> None:
        # 指数退避 + 抖动：避免降级瞬间所有进程同时重打上游
        delay = self.backoff_base * (2**attempt) + random.uniform(0, 0.3)
        await self._sleep(delay)

    def breaker_snapshot(self) -> list[dict[str, object]]:
        return [
            {
                "model": item.model,
                "state": item.state,
                "samples": item.samples,
                "failures": item.failures,
                "failure_rate": item.failure_rate,
            }
            for item in (breaker.snapshot() for breaker in self.breakers.values())
        ]

"""AI 网关：把"提示词 -> 缓存 -> 配额 -> 模型链 -> 校验 -> 降级 -> 审计"串成一条线。

所有 AI 能力都从这里走，接口层只看到三种结果：
1. 拿到结构化数据（used_ai=True，可能来自缓存）；
2. 拿到 None + 降级原因（used_ai=False，调用方用规则/模板兜底）；
3. 配额耗尽抛 42902（这是唯一需要页面显式处理的 AI 错误）。

铁律：**降级不抛异常**。任何供应商故障都收敛成 `(None, meta)`，
页面永远不会因为模型抽风而白屏——这是从旧 Node 版继承的硬约束。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import Settings
from app.core.context import get_request_id
from app.core.errors import AppError, ErrorCode
from app.core.metrics import AI_DEGRADED
from app.domain.enums import DimensionKey, Intent
from app.infra.cache import AICache, build_cache_key
from app.prompts.base import PromptSpec
from app.prompts.debrief import DebriefContext, build_debrief_prompt, parse_debrief
from app.prompts.intent import IntentContext, build_intent_prompt, parse_intent
from app.prompts.persona import (
    PersonaContext,
    build_persona_prompt,
    is_low_quality_persona,
    parse_persona,
)
from app.prompts.score import ScoreContext, build_score_prompt, parse_score
from app.services.audit_service import AuditRecorder
from app.services.llm.base import AllModelsFailed
from app.services.llm.router import ModelRouter
from app.services.llm.usage import UsageTracker

# 降级原因必须是有限集合：否则 Prometheus 标签基数会失控
DEGRADE_LABELS = {
    "no_key",
    "quota",
    "timeout",
    "rate_limited",
    "server_error",
    "network",
    "auth",
    "empty",
    "bad_payload",
    "invalid_output",
    "breaker_open",
    "unknown",
}


@dataclass(slots=True)
class AiMetaData:
    used_ai: bool
    model: str | None = None
    degrade_reason: str | None = None
    latency_ms: int = 0
    cache_hit: bool = False


class AIGateway:
    def __init__(
        self,
        settings: Settings,
        router: ModelRouter,
        cache: AICache,
        quota,
        usage: UsageTracker | None = None,
        audit: AuditRecorder | None = None,
    ) -> None:
        self.settings = settings
        self.router = router
        self.cache = cache
        self.quota = quota
        self.usage = usage or UsageTracker()
        self.audit = audit
        # 全局并发闸门：旧 Node 服务 GLM_CONCURRENCY=2，进程内信号量最直观；
        # 多 worker 部署时配合配额（Redis 计数）一起限制供应商侧压力。
        self._semaphore = asyncio.Semaphore(max(1, settings.glm_concurrency))

    # ── 对外能力 ──
    async def intent(self, ctx: IntentContext, *, account_id=None) -> tuple[Intent | None, AiMetaData]:
        prompt = build_intent_prompt(ctx)
        payload = {
            "stage": ctx.stage,
            "text": ctx.input_text,
            "rule_hint": ctx.rule_hint,
            "name": ctx.name,
        }

        def parse(text: str) -> dict[str, str] | None:
            parsed = parse_intent(text)
            return {"intent": parsed.value} if parsed else None

        data, meta = await self._invoke(
            purpose="intent",
            prompt=prompt,
            parse=parse,
            cache_payload=payload,
            account_id=account_id,
            input_text=ctx.input_text,
        )
        if not isinstance(data, dict):
            return None, meta
        try:
            return Intent(data.get("intent", "")), meta
        except ValueError:
            return None, AiMetaData(False, meta.model, "invalid_output", meta.latency_ms, meta.cache_hit)

    async def persona(self, ctx: PersonaContext, *, account_id=None) -> tuple[str | None, AiMetaData]:
        prompt = build_persona_prompt(ctx)
        payload = {
            "system": ctx.system_prompt,
            "difficulty": ctx.difficulty,
            "emotion": ctx.emotion,
            "history": ctx.history[-6:],
            "said": ctx.said_lines[-6:],
        }

        def parse(text: str) -> dict[str, str] | None:
            line = parse_persona(text, ctx.forbidden)
            if line is None or is_low_quality_persona(line, ctx.emotion):
                return None
            return {"text": line}

        data, meta = await self._invoke(
            purpose="persona",
            prompt=prompt,
            parse=parse,
            cache_payload=payload,
            account_id=account_id,
            input_text=json.dumps(payload["history"], ensure_ascii=False),
        )
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            return None, meta
        return text, meta

    async def score(self, ctx: ScoreContext, *, account_id=None) -> tuple[dict[DimensionKey, dict] | None, AiMetaData]:
        prompt = build_score_prompt(ctx)
        payload = {
            "dialogue": ctx.dialogue[-2000:],
            "stats": dataclasses.asdict(ctx.stats),
        }

        def parse(text: str) -> dict[str, Any] | None:
            parsed = parse_score(text)
            if parsed is None:
                return None
            return {key.value: value for key, value in parsed.items()}

        data, meta = await self._invoke(
            purpose="score",
            prompt=prompt,
            parse=parse,
            cache_payload=payload,
            account_id=account_id,
            input_text=json.dumps(payload, ensure_ascii=False),
        )
        if not isinstance(data, dict):
            return None, meta
        restored: dict[DimensionKey, dict] = {}
        for key in DimensionKey:
            value = data.get(key.value)
            if not isinstance(value, dict):
                return None, AiMetaData(False, meta.model, "invalid_output", meta.latency_ms, meta.cache_hit)
            restored[key] = value
        return restored, meta

    async def debrief(self, ctx: DebriefContext, *, account_id=None) -> tuple[dict[str, Any] | None, AiMetaData]:
        prompt = build_debrief_prompt(ctx)
        payload = {
            "name": ctx.name,
            "scores": ctx.scores,
            "hit_rules": ctx.hit_rules,
            "nickname": ctx.nickname,
        }

        def parse(text: str) -> dict[str, Any] | None:
            return parse_debrief(text)

        data, meta = await self._invoke(
            purpose="debrief",
            prompt=prompt,
            parse=parse,
            cache_payload=payload,
            account_id=account_id,
            input_text=json.dumps(payload, ensure_ascii=False),
        )
        return (data if isinstance(data, dict) else None), meta

    # ── 统一执行 ──
    async def _invoke(
        self,
        *,
        purpose: str,
        prompt: PromptSpec,
        parse: Callable[[str], Any],
        cache_payload: dict[str, Any],
        account_id=None,
        input_text: str = "",
    ) -> tuple[Any, AiMetaData]:
        if not self.settings.ai_configured:
            return await self._degrade(
                purpose, prompt, "no_key", 0, account_id, input_text, output=""
            )

        model = self.settings.glm_model
        key = build_cache_key(purpose, prompt.prompt_version, model, cache_payload)
        cached = await self.cache.get(key)
        if cached is not None:
            try:
                data = json.loads(cached)
            except ValueError:
                data = None
            if data is not None:
                meta = AiMetaData(True, model, None, 0, True)
                await self.usage.record_cache_hit()
                await self._audit(purpose, prompt, meta, json.dumps(data, ensure_ascii=False), account_id, input_text)
                return data, meta

        # 配额是唯一允许冒泡的 AI 错误：页面必须知道"今天不能再调了"
        await self.quota.consume()

        started = time.perf_counter()
        try:
            async with self._semaphore:
                response = await self.router.complete(
                    purpose=purpose,
                    system=prompt.system,
                    user=prompt.user,
                    json_mode=prompt.json_mode,
                    max_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                )
        except AllModelsFailed as exc:
            latency = int((time.perf_counter() - started) * 1000)
            return await self._degrade(
                purpose, prompt, exc.reason, latency, account_id, input_text, output=exc.detail
            )

        latency = int((time.perf_counter() - started) * 1000) or response.latency_ms
        await self.usage.record_call(
            purpose,
            ok=True,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
        )

        try:
            data = parse(response.text)
        except Exception:  # noqa: BLE001 —— 解析器不允许把接口打挂
            data = None

        if data is None:
            return await self._degrade(
                purpose, prompt, "invalid_output", latency, account_id, input_text, output=response.text
            )

        await self.cache.set(key, json.dumps(data, ensure_ascii=False))
        meta = AiMetaData(True, response.model, None, latency, False)
        await self._audit(purpose, prompt, meta, response.text, account_id, input_text)
        return data, meta

    async def _degrade(
        self,
        purpose: str,
        prompt: PromptSpec,
        reason: str,
        latency_ms: int,
        account_id,
        input_text: str,
        *,
        output: str = "",
    ) -> tuple[None, AiMetaData]:
        label = reason if reason in DEGRADE_LABELS else "unknown"
        AI_DEGRADED.labels(label).inc()
        await self.usage.record_call(purpose, ok=False)
        await self.usage.record_degraded()
        meta = AiMetaData(False, None, label, latency_ms, False)
        await self._audit(purpose, prompt, meta, output, account_id, input_text)
        return None, meta

    async def _audit(
        self,
        purpose: str,
        prompt: PromptSpec,
        meta: AiMetaData,
        output_text: str,
        account_id,
        input_text: str,
    ) -> None:
        if self.audit is None:
            return
        await self.audit.record(
            purpose=purpose,
            provider=self.router.provider.name,
            model=meta.model,
            status="ok" if meta.used_ai else "degraded",
            used_ai=meta.used_ai,
            degrade_reason=meta.degrade_reason,
            prompt_version=prompt.prompt_version,
            input_text=input_text,
            output_text=output_text,
            latency_ms=meta.latency_ms,
            cache_hit=meta.cache_hit,
            account_id=account_id,
            request_id=get_request_id(),
        )

    # ── 只读视图（健康检查 / 运维） ──
    async def usage_snapshot(self) -> dict[str, Any]:
        return await self.usage.snapshot()

    async def quota_snapshot(self) -> dict[str, int]:
        return await self.quota.snapshot()

    @property
    def breaker_snapshot(self) -> list[dict[str, object]]:
        return self.router.breaker_snapshot()

    @property
    def cache_stats(self) -> dict[str, int]:
        return self.cache.stats

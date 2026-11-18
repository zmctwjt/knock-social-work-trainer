"""旧接口兼容层：`/api/health`、`/api/usage`、`/api/selftest`、`/api/ai/*`。

绞杀者策略（ADR-07）：新旧两套接口在同一进程里**双跑**，同一套 service/网关；
旧层只是把 v1 的结果翻译回旧响应形状，并加 `Deprecation` 响应头。
前端不需要改一行就能继续用；灰度期结束后整层删除。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.deps import GatewayDep, QuotaDep, UsageDep, ai_rate_limit
from app.core.deps import SettingsDep
from app.domain.enums import Difficulty, DimensionKey, Intent, RiskLevel
from app.domain.rules import match_local_rules
from app.domain.scoring import DialogMessage  # noqa: F401  —— 保持领域口径可见
from app.prompts.debrief import DebriefContext
from app.prompts.intent import IntentContext
from app.prompts.persona import PersonaContext
from app.prompts.score import ScoreContext, ScoreStats
from app.core.errors import AppError, ErrorCode
from app.services.llm.quota import quota_date

router = APIRouter(prefix="/api", tags=["兼容层"])

_LEGACY_CODES = {
    ErrorCode.BAD_REQUEST: "BAD_INPUT",
    ErrorCode.UNAUTHORIZED: "UNAUTHORIZED",
    ErrorCode.FORBIDDEN: "FORBIDDEN",
    ErrorCode.NOT_FOUND: "NOT_FOUND",
    ErrorCode.CONFLICT: "CONFLICT",
    ErrorCode.RATE_LIMITED: "RPM",
    ErrorCode.AI_QUOTA_EXCEEDED: "DAILY_CAP",
    ErrorCode.AI_UNAVAILABLE: "UPSTREAM",
    ErrorCode.INTERNAL: "INTERNAL",
}

_DIFFICULTY_BY_LABEL = {
    "简单实习": 2,
    "标准实训": 3,
    "挑战督导": 4,
}


def _headers() -> dict[str, str]:
    return {
        "Deprecation": "true",
        "Link": '</api/v1/ai>; rel="successor-version"',
        "Sunset": "Wed, 31 Dec 2026 23:59:59 GMT",
        "X-Knock-Api": "legacy",
    }


def _str(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _num(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value)


def _error(exc: AppError) -> JSONResponse:
    code = _LEGACY_CODES.get(exc.code, "INTERNAL")
    return JSONResponse(
        status_code=exc.http_status,
        content={"ok": False, "usedAI": False, "error": {"code": code, "message": exc.message}},
        headers=_headers(),
    )


def _bad_input(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"ok": False, "usedAI": False, "error": {"code": "BAD_INPUT", "message": message}},
        headers=_headers(),
    )


async def _usage_payload(usage: UsageDep) -> dict[str, Any]:
    return await usage.snapshot()


@router.get("/health", summary="旧版健康检查", deprecated=True)
async def legacy_health(
    settings: SettingsDep,
    usage: UsageDep,
    quota: QuotaDep,
) -> JSONResponse:
    try:
        used = await quota.used()
        remaining = await quota.remaining()
    except Exception:  # noqa: BLE001 —— 健康检查永不 500
        used, remaining = -1, -1
    body = {
        "ok": True,
        "ai": {
            "configured": settings.ai_configured,
            "model": settings.glm_model,
            "fallback": settings.fallback_model_list,
            "thinking": "disabled",
            "timeoutMs": settings.glm_timeout_ms,
        },
        "usage": {
            **await _usage_payload(usage),
            "date": quota_date(),
            "usedToday": used,
            "remainingToday": remaining,
            "dailyCap": settings.glm_daily_cap,
            "rpmPerIp": settings.glm_rpm_per_ip,
            "concurrency": settings.glm_concurrency,
        },
        "server": {"port": settings.port, "uptimeSec": int(time.time() - getattr(settings, "_started", time.time()))},
    }
    return JSONResponse(content=body, headers=_headers())


@router.get("/usage", summary="旧版用量查询", deprecated=True)
async def legacy_usage(
    settings: SettingsDep, usage: UsageDep, quota: QuotaDep
) -> JSONResponse:
    try:
        used = await quota.used()
        remaining = await quota.remaining()
    except Exception:  # noqa: BLE001
        used, remaining = -1, -1
    body = {
        "ok": True,
        "usage": {
            **await _usage_payload(usage),
            "date": quota_date(),
            "usedToday": used,
            "remainingToday": remaining,
            "dailyCap": settings.glm_daily_cap,
        },
    }
    return JSONResponse(content=body, headers=_headers())


@router.post(
    "/selftest",
    summary="旧版链路自检",
    deprecated=True,
    dependencies=[Depends(ai_rate_limit)],
)
async def legacy_selftest(settings: SettingsDep) -> JSONResponse:
    started = time.perf_counter()
    cases = [
        ("你最近睡得好吗？", Intent.OPEN_QUESTION),
        ("你怎么又这样，我早说了吧", Intent.JUDGE),
        ("我理解。", Intent.EMPATHY),
        ("你先别急，听我的，明天就去辞职", Intent.ADVICE_TOO_EARLY),
        ("（沉默）", Intent.SILENCE),
        ("今天天气不错", Intent.OFF_TOPIC),
        ("我不想活了", Intent.CRISIS),
    ]
    results = []
    passed = 0
    for text, expected in cases:
        matched = match_local_rules(text)
        ok = matched.intent == expected
        passed += 1 if ok else 0
        results.append(
            {
                "input": text,
                "intent": matched.intent.value,
                "expected": expected.value,
                "risk": matched.risk_level.value,
                "ok": ok,
            }
        )
    body = {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": results,
        "model": settings.glm_model if settings.ai_configured else "",
        "ms": int((time.perf_counter() - started) * 1000),
        "detail": "规则层自检不依赖外部模型，可用于部署后快速验证",
    }
    return JSONResponse(content=body, headers=_headers())


@router.post(
    "/ai/intent",
    summary="旧版意图判定",
    deprecated=True,
    dependencies=[Depends(ai_rate_limit)],
)
async def legacy_intent(
    settings: SettingsDep,
    gateway: GatewayDep,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> JSONResponse:
    text = _str(payload.get("input"), 600)
    if not text:
        return _bad_input("input 不能为空")

    rule = match_local_rules(text)
    if rule.risk_level is not RiskLevel.NONE:
        return JSONResponse(
            content={
                "ok": True,
                "usedAI": False,
                "intent": rule.intent.value,
                "degradeReason": "crisis_blocked",
                "model": None,
                "ms": 0,
                "cached": False,
            },
            headers=_headers(),
        )

    hint = None
    raw_hint = _str(payload.get("ruleHint"), 40)
    if raw_hint:
        try:
            hint = Intent(raw_hint)
        except ValueError:
            hint = None

    ctx = IntentContext(
        input_text=text,
        stage=_str(payload.get("stage"), 40),
        name=_str(payload.get("name"), 40),
        age=_num(payload.get("age"), 0),
        identity=_str(payload.get("identity"), 80),
        brief=_str(payload.get("brief"), 200),
        rule_hint=hint,
    )
    try:
        intent, meta = await gateway.intent(ctx)
    except AppError as exc:
        return _error(exc)
    body = {
        "ok": intent is not None,
        "usedAI": intent is not None,
        "intent": intent.value if intent else None,
        "model": meta.model,
        "ms": meta.latency_ms,
        "cached": meta.cache_hit,
    }
    return JSONResponse(content=body, headers=_headers())


@router.post(
    "/ai/persona",
    summary="旧版角色扮演",
    deprecated=True,
    dependencies=[Depends(ai_rate_limit)],
)
async def legacy_persona(
    gateway: GatewayDep,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> JSONResponse:
    system_prompt = _str(payload.get("systemPrompt"), 4000)
    if len(system_prompt) < 10:
        return _bad_input("人设提示词缺失")

    difficulty = _DIFFICULTY_BY_LABEL.get(_str(payload.get("difficultyLabel"), 20), 3)
    forbidden = [
        _str(item, 40) for item in (payload.get("forbidden") or []) if _str(item, 40)
    ][:8]
    history = [
        ("worker" if (item or {}).get("role") == "worker" else "client", _str((item or {}).get("text"), 600))
        for item in (payload.get("history") or [])[-20:]
        if isinstance(item, dict)
    ]
    said_lines = [_str(item, 200) for item in (payload.get("saidLines") or [])[-6:] if _str(item, 200)]

    ctx = PersonaContext(
        system_prompt=system_prompt,
        difficulty=difficulty,
        emotion=_num(payload.get("emotion"), 45),
        voice_text=_str(payload.get("voiceByEmotion"), 300),
        phase=_num(payload.get("phase"), 1),
        forbidden=forbidden,
        history=history,
        said_lines=said_lines,
    )
    try:
        text, meta = await gateway.persona(ctx)
    except AppError as exc:
        return _error(exc)
    body = {
        "ok": text is not None,
        "usedAI": text is not None,
        "text": text,
        "model": meta.model,
        "ms": meta.latency_ms,
        "cached": meta.cache_hit,
    }
    return JSONResponse(content=body, headers=_headers())


@router.post(
    "/ai/score",
    summary="旧版六维评分",
    deprecated=True,
    dependencies=[Depends(ai_rate_limit)],
)
async def legacy_score(
    gateway: GatewayDep,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> JSONResponse:
    dialogue = _str(payload.get("dialogue"), 8000)
    if not dialogue:
        return _bad_input("dialogue 不能为空")

    raw_stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    stats = ScoreStats(
        worker_turns=_num(raw_stats.get("workerTurns"), 0),
        judge_count=_num(raw_stats.get("judgeCount"), 0),
        hopeless_seen=_bool(raw_stats.get("hopelessSeen")),
        hopeless_recognized=_bool(raw_stats.get("hopelessRecognized")),
        crisis_seen=_bool(raw_stats.get("crisisSeen")),
    )
    if stats.crisis_seen:
        return JSONResponse(
            content={
                "ok": True,
                "usedAI": False,
                "scores": None,
                "model": None,
                "ms": 0,
                "cached": False,
            },
            headers=_headers(),
        )

    try:
        raw, meta = await gateway.score(ScoreContext(dialogue=dialogue, stats=stats))
    except AppError as exc:
        return _error(exc)

    scores = None
    if raw is not None:
        scores = {key.value: value for key, value in raw.items()}
    body = {
        "ok": scores is not None,
        "usedAI": scores is not None,
        "scores": scores,
        "model": meta.model,
        "ms": meta.latency_ms,
        "cached": meta.cache_hit,
    }
    return JSONResponse(content=body, headers=_headers())


@router.post(
    "/ai/debrief",
    summary="旧版复盘报告",
    deprecated=True,
    dependencies=[Depends(ai_rate_limit)],
)
async def legacy_debrief(
    gateway: GatewayDep,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> JSONResponse:
    scores: dict[DimensionKey, int] = {}
    raw_scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    for name, value in raw_scores.items():
        try:
            scores[DimensionKey(name)] = _num(value, 60)
        except ValueError:
            continue
    hit_rules = [_str(item, 160) for item in (payload.get("hitRules") or [])[:12]]

    ctx = DebriefContext(
        nickname=_str(payload.get("nickname"), 30) or "同学",
        name=_str(payload.get("name"), 40),
        age=_num(payload.get("age"), 0),
        identity=_str(payload.get("identity"), 80),
        scores=scores,
        hit_rules=hit_rules,
    )
    try:
        report, meta = await gateway.debrief(ctx)
    except AppError as exc:
        return _error(exc)

    body = {
        "ok": report is not None,
        "usedAI": report is not None,
        "report": (
            {
                "strength": report["strength"],
                "improvement": report["improvement"],
                "nextStep": report["next_step"],
            }
            if report
            else None
        ),
        "model": meta.model,
        "ms": meta.latency_ms,
        "cached": meta.cache_hit,
    }
    return JSONResponse(content=body, headers=_headers())


__all__ = ["router", "match_local_rules", "Difficulty"]

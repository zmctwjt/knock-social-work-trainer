"""v1 AI 链路：意图判定、角色扮演、分段评分、三段式复盘。

这一层刻意薄：只做「请求 → 领域上下文 → 网关 → 响应包」，
所有降级、缓存、配额、熔断都在 `AIGateway` 内完成。
两条铁律在入口处执行：
1. 危机内容不调模型（本地规则先判，命中即返回规则结果）；
2. 任何 AI 失败都不返回 null 给页面——用规则分/模板文案兜底，并标注 used_ai=False。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import GatewayDep, ai_rate_limit
from app.core.deps import SessionDep
from app.core.metrics import CRISIS_BLOCKED
from app.core.response import ok
from app.domain.enums import (
    DIMENSION_ORDER,
    DimensionKey,
    RiskLevel,
    ScoreSource,
    Speaker,
)
from app.domain.schemas import (
    AiMeta,
    DebriefRequest,
    DebriefSectionsOut,
    Envelope,
    IntentOut,
    IntentRequest,
    PersonaOut,
    PersonaRequest,
    ScoreOut,
    ScoreRequest,
)
from app.domain.scoring import (
    DialogMessage,
    RuleScoreInput,
    collect_utterances,
    compute_rule_score,
    find_weakness,
    merge_scores,
    safe_score,
    weighted_total,
)
from app.domain.rules import match_local_rules
from app.prompts.debrief import DebriefContext
from app.prompts.intent import IntentContext
from app.prompts.persona import PersonaContext
from app.prompts.score import ScoreContext, ScoreStats
from app.services import content_service
from app.services.ai_gateway import AiMetaData

router = APIRouter(
    prefix="/ai",
    tags=["AI 链路"],
    dependencies=[Depends(ai_rate_limit)],
)

_EMPTY_META = AiMetaData(used_ai=False, model=None, degrade_reason=None, latency_ms=0)


def _meta(meta: AiMetaData) -> AiMeta:
    return AiMeta(
        used_ai=meta.used_ai,
        model=meta.model,
        degrade_reason=meta.degrade_reason,
        latency_ms=meta.latency_ms,
        cache_hit=meta.cache_hit,
    )


def _scores_out(scores: dict[DimensionKey, int]) -> dict[str, int]:
    return {key.value: safe_score(value) for key, value in scores.items()}


def _persona_history(payload: PersonaRequest) -> list[tuple[str, str]]:
    return [(item.role, item.text) for item in payload.history][-20:]


def _max_risk(messages) -> str:
    """取对话中最高风险等级，用作 crisis_blocked_total 的 risk_level 标签。"""
    level = "suicidal"
    for item in messages:
        risk = match_local_rules(item.text).risk_level
        if risk is RiskLevel.HOPELESSNESS:
            level = risk.value
        elif risk is RiskLevel.SUICIDAL:
            return risk.value
    return level


@router.post("/intent", response_model=Envelope[IntentOut], summary="判定学生意图")
async def judge_intent(payload: IntentRequest, session: SessionDep, gateway: GatewayDep):
    rule = match_local_rules(payload.input)
    name, age, identity, brief = "服务对象", 40, "社区居民", ""

    if payload.scenario_id:
        scenario = await content_service.get_scenario(session, payload.scenario_id)
        name, age, identity, brief = (
            scenario.name,
            scenario.age,
            scenario.archetype,
            scenario.brief,
        )

    # 铁律一：危机内容永不调模型
    if rule.risk_level is not RiskLevel.NONE:
        CRISIS_BLOCKED.labels(rule.risk_level.value, "ai_intent").inc()
        out = IntentOut(
            intent=rule.intent,
            rule_hint=rule.intent,
            source="rule",
            meta=_meta(
                AiMetaData(
                    used_ai=False,
                    model=None,
                    degrade_reason="crisis_blocked",
                    latency_ms=0,
                )
            ),
        )
        return ok(out)

    ctx = IntentContext(
        input_text=payload.input,
        stage=payload.stage or "第 1 阶段",
        name=name,
        age=age,
        identity=identity,
        brief=brief,
        rule_hint=rule.intent,
    )
    ai_intent, meta = await gateway.intent(ctx)
    out = IntentOut(
        intent=ai_intent or rule.intent,
        rule_hint=rule.intent,
        source="ai" if ai_intent is not None else "rule",
        meta=_meta(meta),
    )
    return ok(out)


@router.post("/persona", response_model=Envelope[PersonaOut], summary="生成角色台词")
async def play_persona(payload: PersonaRequest, session: SessionDep, gateway: GatewayDep):
    scenario = await content_service.get_scenario(session, payload.scenario_id)
    emotion = payload.emotion
    voice = scenario.voice_for(emotion)

    ctx = PersonaContext(
        system_prompt=scenario.system_prompt,
        difficulty=payload.difficulty or scenario.difficulty,
        emotion=emotion,
        voice_text=voice,
        phase=payload.phase,
        forbidden=list(scenario.forbidden or []),
        history=_persona_history(payload),
        said_lines=list(payload.said_lines)[-6:],
    )
    text, meta = await gateway.persona(ctx)

    # 铁律二：AI 失败也必须给页面一句可读的台词（用情绪档兜底）
    if text is None:
        return ok(PersonaOut(text=voice, meta=_meta(meta)))
    return ok(PersonaOut(text=text, meta=_meta(meta)))


def _dialogue(payload: ScoreRequest) -> list[DialogMessage]:
    messages: list[DialogMessage] = []
    for item in payload.dialogue:
        try:
            speaker = Speaker(item.role)
        except ValueError:
            speaker = Speaker.WORKER
        messages.append(DialogMessage(speaker=speaker, text=item.text))
    return messages


def _rule_scores_for(payload: ScoreRequest):
    messages = _dialogue(payload)
    collected = collect_utterances(messages)
    rule = compute_rule_score(
        RuleScoreInput(
            utterances=collected.utterances,
            hopeless_detected=collected.hopeless_seen,
            hopeless_recognized=collected.hopeless_recognized,
            total_stages=payload.total_stages,
            completed_stages=payload.completed_stages,
            judge_count=collected.judge_count,
            vague_empathy_count=collected.vague_empathy_count,
        )
    )
    stats = ScoreStats(
        worker_turns=collected.worker_turns,
        judge_count=collected.judge_count,
        hopeless_seen=collected.hopeless_seen,
        hopeless_recognized=collected.hopeless_recognized,
        crisis_seen=collected.crisis_seen,
    )
    return messages, collected, rule, stats


@router.post("/score", response_model=Envelope[ScoreOut], summary="六维评分")
async def score_dialogue(payload: ScoreRequest, gateway: GatewayDep):
    messages, collected, rule, stats = _rule_scores_for(payload)

    ai_scores: dict[DimensionKey, int] | None = None
    meta = AiMetaData(used_ai=False, model=None, degrade_reason=None)
    if not collected.crisis_seen:
        dialogue_text = "\n".join(
            ("学生" if item.speaker == Speaker.WORKER else "服务对象") + "：" + item.text
            for item in messages
        )
        ai_raw, meta = await gateway.score(ScoreContext(dialogue=dialogue_text[-4000:], stats=stats))
        if ai_raw is not None:
            ai_scores = {
                key: safe_score(value.get("score")) for key, value in ai_raw.items()
            }
    else:
        CRISIS_BLOCKED.labels(_max_risk(messages), "ai_score").inc()
        meta = AiMetaData(used_ai=False, model=None, degrade_reason="crisis_blocked")

    merged = merge_scores(rule, ai_scores)
    total = weighted_total(merged.scores)
    source = ScoreSource.BLEND if merged.used_ai else ScoreSource.RULE
    out = ScoreOut(
        scores=_scores_out(merged.scores),
        total=total,
        source=source,
        used_ai=merged.used_ai,
        missing=[key.value for key in merged.missing],
        meta=_meta(meta),
    )
    return ok(out)


def _scores_from_request(raw: dict[str, int]) -> dict[DimensionKey, int]:
    result: dict[DimensionKey, int] = {key: 60 for key in DIMENSION_ORDER}
    for name, value in raw.items():
        try:
            result[DimensionKey(name)] = safe_score(value, 60)
        except ValueError:
            continue
    return result


@router.post("/debrief", response_model=Envelope[DebriefSectionsOut], summary="三段式复盘")
async def debrief(payload: DebriefRequest, gateway: GatewayDep):
    scores = _scores_from_request(payload.scores)
    ctx = DebriefContext(
        nickname=payload.nickname or "同学",
        name="服务对象",
        age=40,
        identity="社区居民",
        scores=scores,
        hit_rules=list(payload.hit_rules)[:20],
    )
    sections, meta = await gateway.debrief(ctx)
    if sections is None:
        weakness = find_weakness(scores)
        advice = weakness.advice or f"下一次先把「{weakness.name}」练稳。"
        sections = {
            "strength": "能持续把对话推进下去，并愿意在关键处停下来观察服务对象的反应。",
            "improvement": f"相对薄弱的是{weakness.name}，容易急着给建议而漏掉情绪线索。",
            "next_step": advice,
        }
    return ok(
        DebriefSectionsOut(
            strength=sections["strength"],
            improvement=sections["improvement"],
            next_step=sections["next_step"],
            meta=_meta(meta),
        )
    )


__all__ = ["router", "classify_risk", "Intent"]

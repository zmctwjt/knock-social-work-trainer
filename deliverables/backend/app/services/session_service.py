"""训练会话服务：发言、分段评分、结案、复盘。

这一层是行为基准的"翻译层"：把 Node 版前端里的编排逻辑
（意图判定 → 扮演 → 情绪联动 → 规则计分 → 0.4/0.6 融合）
收进服务端，接口层只剩参数校验与响应组装。

两条铁律在这里落地：
1. `match_local_rules` 判定为危机时**直接短路**，不构造任何提示词、
   不调用网关——本地硬拦截先于模型；
2. 任何 AI 失败都退化成规则/模板结果，绝不把异常抛给页面。
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.metrics import (
    CRISIS_BLOCKED,
    SCORE_OVERALL,
    TRAINING_COMPLETED,
    TRAINING_STARTED,
)
from app.domain.crisis import CrisisCard, build_crisis_card, build_suggestion
from app.domain.enums import (
    DimensionKey,
    Intent,
    RiskLevel,
    ScoreSource,
    SessionStatus,
    Speaker,
)
from app.domain.models import (
    Account,
    Debrief,
    StageScore,
    TrainingRecord,
    TrainingSession,
    Turn,
)
from app.domain.rules import MatchResult, effects_for_intent, match_local_rules
from app.domain.schemas import CrisisCardOut
from app.domain.scoring import (
    BASE_SCORES,
    INTENT_TO_DIMENSION,
    DialogMessage,
    RuleScoreInput,
    build_margin_notes,
    collect_utterances,
    compute_rule_score,
    find_weakness,
    merge_scores,
    weighted_total,
)
from app.domain.schemas import (
    DebriefOut as DebriefSchema,
    FinishOut as FinishSchema,
    ProofMarkOut,
    ScoringOut,
    SessionDetailOut,
    SessionOut,
    StageScoreOut,
    SuggestionOut,
    TurnOut,
    TurnPairOut,
    difficulty_label_of,
)
from app.prompts.debrief import DebriefContext
from app.prompts.intent import IntentContext
from app.prompts.persona import PersonaContext
from app.prompts.score import ScoreContext, ScoreStats
from app.services.ai_gateway import AIGateway, AiMetaData
from app.services.content_service import get_scenario

MAX_EMOTION = 100
MIN_EMOTION = 0

FALLBACK_REPLIES = {
    "low": ["……（沉默了一会儿）", "嗯。", "我不太想说这个。"],
    "mid": ["……你说。", "嗯，然后呢？", "我听着呢。"],
    "high": ["你接着说，我在听。", "这事儿说起来就一肚子话。", "嗯，你继续说。"],
}


# ═══════════════════════════════════════════════════════════
# 一、查询与授权
# ═══════════════════════════════════════════════════════════


async def load_owned_session(
    session: AsyncSession, account: Account, session_id: uuid.UUID
) -> TrainingSession:
    """用应用层 `owner_id` 过滤替代原 Supabase RLS：越权返回 40301 而不是 404。"""
    model = await session.get(TrainingSession, session_id)
    if model is None:
        raise AppError.not_found("训练会话不存在")
    if model.owner_id != account.id:
        raise AppError.forbidden("无权访问他人的训练会话")
    return model


async def _load_turns(session: AsyncSession, session_id: uuid.UUID) -> list[Turn]:
    rows = await session.execute(
        select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index)
    )
    return list(rows.scalars().all())


async def _scenario_name(session: AsyncSession, scenario_id: str) -> str:
    from app.domain.models import Scenario

    scenario = await session.get(Scenario, scenario_id)
    return scenario.name if scenario else scenario_id


def _session_out(model: TrainingSession, scenario_name: str) -> SessionOut:
    return SessionOut(
        id=model.id,
        scenario_id=model.scenario_id,
        scenario_name=scenario_name,
        status=SessionStatus(model.status),
        difficulty=model.difficulty,
        difficulty_label=difficulty_label_of(model.difficulty),
        blindfold=model.blindfold,
        ui_phase=model.ui_phase,
        emotion=model.emotion,
        turn_count=model.turn_count,
        max_turns=model.max_turns,
        crisis_flag=model.crisis_flag,
        total_score=model.total_score,
        used_ai=model.used_ai,
        created_at=model.created_at,
        finished_at=model.finished_at,
    )


def _crisis_card_out(card) -> CrisisCardOut | None:
    if card is None:
        return None
    if isinstance(card, dict):
        # meta 落库是 JSON，回读时是 dict；此处统一成响应模型
        hotlines = [
            item
            if isinstance(item, dict)
            else {"code": item.code, "label": item.label}
            for item in card.get("hotlines", [])
        ]
        return CrisisCardOut(
            level=card.get("level", ""),
            title=card.get("title", ""),
            principles=list(card.get("principles", [])),
            hotlines=hotlines,
            citation=card.get("citation"),
            disclaimer=card.get("disclaimer"),
        )
    return CrisisCardOut(
        level=card.level,
        title=card.title,
        principles=list(card.principles),
        hotlines=[{"code": item.code, "label": item.label} for item in card.hotlines],
        citation=card.citation,
        disclaimer=card.disclaimer,
    )


def _suggestion_out(card) -> SuggestionOut | None:
    if card is None:
        return None
    return SuggestionOut(title=card.title, quote=card.quote, basis=card.basis)


def _turn_out(turn: Turn) -> TurnOut:
    meta = turn.meta or {}
    marks = [
        ProofMarkOut(kind=str(item.get("kind", "")), start=int(item.get("start", 0)), end=int(item.get("end", 0)))
        for item in (turn.marks or [])
    ]
    return TurnOut(
        id=turn.id,
        turn_index=turn.turn_index,
        speaker=Speaker(turn.speaker),
        text=turn.text,
        intent=Intent(turn.intent) if turn.intent else None,
        dimension=DimensionKey(turn.dimension) if turn.dimension else None,
        delta=turn.delta,
        rule_note=turn.rule_note or "",
        source=turn.source,
        marks=marks,
        is_crisis=turn.is_crisis,
        emotion_after=int(meta.get("emotion_after", 50)),
        used_ai=bool(meta.get("used_ai", False)),
        degraded=bool(meta.get("degraded", False)),
        suggestion=_suggestion_out_dict(meta.get("suggestion")),
        crisis_card=_crisis_card_out(meta.get("crisis_card")),
        risk_level=RiskLevel(meta.get("risk_level", RiskLevel.NONE.value)),
    )


def _suggestion_out_dict(raw: dict[str, Any] | None) -> SuggestionOut | None:
    if not raw:
        return None
    return SuggestionOut(
        title=str(raw.get("title", "")),
        quote=str(raw.get("quote", "")),
        basis=str(raw.get("basis", "")),
    )


def _card_dict(card: CrisisCard | None) -> dict[str, Any] | None:
    if card is None:
        return None
    return {
        "level": card.level,
        "title": card.title,
        "principles": list(card.principles),
        "hotlines": [{"code": item.code, "label": item.label} for item in card.hotlines],
        "citation": card.citation,
        "disclaimer": card.disclaimer,
    }


# ═══════════════════════════════════════════════════════════
# 二、创建与列表
# ═══════════════════════════════════════════════════════════


async def create_session(
    session: AsyncSession,
    account: Account,
    *,
    scenario_id: str,
    difficulty: int | None,
    blindfold: bool,
    max_turns: int,
    client_session_id: str | None,
) -> SessionOut:
    scenario = await get_scenario(session, scenario_id)

    if client_session_id:
        existing = (
            await session.execute(
                select(TrainingSession).where(
                    TrainingSession.owner_id == account.id,
                    TrainingSession.client_session_id == client_session_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return _session_out(existing, scenario.name)

    model = TrainingSession(
        id=uuid.uuid4(),
        owner_id=account.id,
        scenario_id=scenario.id,
        status=SessionStatus.ACTIVE.value,
        difficulty=difficulty or scenario.difficulty,
        blindfold=blindfold,
        ui_phase=1,
        emotion=scenario.initial_emotion,
        turn_count=0,
        max_turns=max_turns,
        crisis_flag=False,
        used_ai=False,
        client_session_id=client_session_id,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    TRAINING_STARTED.labels(scenario.id, difficulty_label_of(model.difficulty)).inc()
    return _session_out(model, scenario.name)


async def list_sessions(
    session: AsyncSession,
    account: Account,
    *,
    status: SessionStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[SessionOut]:
    stmt = (
        select(TrainingSession)
        .where(TrainingSession.owner_id == account.id)
        .order_by(TrainingSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(TrainingSession.status == status.value)
    rows = list((await session.execute(stmt)).scalars().all())
    names = {row.scenario_id: await _scenario_name(session, row.scenario_id) for row in rows}
    return [_session_out(row, names[row.scenario_id]) for row in rows]


async def get_session_detail(
    session: AsyncSession, account: Account, session_id: uuid.UUID
) -> SessionDetailOut:
    model = await load_owned_session(session, account, session_id)
    turns = await _load_turns(session, model.id)
    stage_rows = list(
        (
            await session.execute(
                select(StageScore)
                .where(StageScore.session_id == model.id)
                .order_by(StageScore.stage_index)
            )
        )
        .scalars()
        .all()
    )
    return SessionDetailOut(
        session=_session_out(model, await _scenario_name(session, model.scenario_id)),
        turns=[_turn_out(turn) for turn in turns],
        stage_scores=[
            StageScoreOut(
                stage_index=row.stage_index,
                scores={str(key): int(value) for key, value in (row.scores or {}).items()},
                total=row.total,
                source=ScoreSource(row.source),
                used_ai=row.used_ai,
            )
            for row in stage_rows
        ],
    )


# ═══════════════════════════════════════════════════════════
# 三、一次发言（核心链路）
# ═══════════════════════════════════════════════════════════


def _clamp_emotion(value: int) -> int:
    return max(MIN_EMOTION, min(MAX_EMOTION, value))


def _fallback_reply(emotion: int, turn_index: int, scenario_id: str = "") -> str:
    """按情绪档取台词。优先用管理端维护的台词，没有则回落基线常量。

    库不可用时 `OVERLAY` 为空，行为与原来完全一致——这是"内容可维护"
    不牺牲"对话永远能推进"的关键。
    """
    bucket = "low" if emotion < 40 else ("high" if emotion >= 70 else "mid")
    from app.services.script_line_service import OVERLAY

    maintained = OVERLAY.lines_for(scenario_id, bucket) if scenario_id else []
    lines = maintained or FALLBACK_REPLIES[bucket]
    return lines[turn_index % len(lines)]


#: 公开别名：AI 链路降级时也要给"真正的台词"，
#: 而 voice_for() 给的是性格描述（"愿意聊家常…"），学生没法接话。
fallback_reply = _fallback_reply


def _apply_rule_score(turn: Turn, intent: Intent) -> None:
    effect = effects_for_intent(intent)
    dimension = INTENT_TO_DIMENSION.get(intent)
    turn.dimension = dimension.value if dimension else None
    turn.delta = effect.score_deltas.get(dimension, 0) if dimension else 0
    if not turn.rule_note:
        turn.rule_note = effect.note


def _history_pairs(turns: list[Turn], limit: int = 20) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for turn in turns[-limit:]:
        role = "worker" if turn.speaker == Speaker.WORKER.value else "client"
        pairs.append((role, turn.text))
    return pairs


async def _replay_pair(
    session: AsyncSession, model: TrainingSession, worker: Turn
) -> TurnPairOut:
    rows = await _load_turns(session, model.id)
    client = next((item for item in rows if item.turn_index == worker.turn_index + 1), None)
    return TurnPairOut(
        worker=_turn_out(worker),
        client=_turn_out(client) if client is not None else None,
        session=_session_out(model, await _scenario_name(session, model.scenario_id)),
        paused=bool(model.crisis_flag),
    )


async def submit_turn(
    session: AsyncSession,
    account: Account,
    session_id: uuid.UUID,
    *,
    text: str,
    client_turn_id: str | None = None,
    stage: int | None = None,
    gateway: AIGateway,
) -> TurnPairOut:
    model = await load_owned_session(session, account, session_id)
    if model.status != SessionStatus.ACTIVE.value:
        raise AppError.conflict("会话已结束，不能继续发言")

    # 幂等：同一个 client_turn_id 重复提交返回首次结果
    if client_turn_id:
        existing = (
            await session.execute(
                select(Turn).where(
                    Turn.session_id == model.id,
                    Turn.client_turn_id == client_turn_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _replay_pair(session, model, existing)

    scenario = await get_scenario(session, model.scenario_id)
    turns = await _load_turns(session, model.id)
    matched: MatchResult = match_local_rules(text)
    risk = matched.risk_level
    is_crisis = risk != RiskLevel.NONE or matched.intent == Intent.CRISIS

    if stage is not None:
        model.ui_phase = stage

    used_ai = False
    degraded = False
    worker_source = "rule"
    reply: str | None = None
    intent = matched.intent

    if is_crisis:
        # 危机硬拦截：不调用任何模型
        intent = Intent.CRISIS
        worker_source = "rule"
        CRISIS_BLOCKED.labels(risk.value, "session").inc()
    else:
        intent_ctx = IntentContext(
            input_text=text,
            stage=f"第{model.ui_phase}阶段",
            name=scenario.name,
            age=scenario.age,
            identity=scenario.archetype,
            brief=scenario.brief,
            rule_hint=matched.intent.value,
        )
        ai_intent, intent_meta = await gateway.intent(intent_ctx, account_id=account.id)
        if ai_intent is not None:
            intent = ai_intent
        if intent_meta.used_ai:
            used_ai = True
        else:
            degraded = True

        said_lines = [item.text for item in turns if item.speaker == Speaker.CLIENT.value][-6:]
        persona_ctx = PersonaContext(
            system_prompt=scenario.system_prompt,
            difficulty=model.difficulty,
            emotion=model.emotion,
            voice_text=scenario.voice_for(model.emotion),
            phase=model.ui_phase,
            forbidden=list(scenario.forbidden or []),
            history=_history_pairs(turns),
            said_lines=said_lines,
        )
        reply, persona_meta = await gateway.persona(persona_ctx, account_id=account.id)
        if persona_meta.used_ai:
            used_ai = True
            worker_source = "ai"
        else:
            degraded = True

    effect = effects_for_intent(intent)
    emotion_after = _clamp_emotion(model.emotion + effect.emotion_delta)
    base_index = model.turn_count * 2

    worker = Turn(
        id=uuid.uuid4(),
        session_id=model.id,
        turn_index=base_index,
        speaker=Speaker.WORKER.value,
        text=text,
        intent=intent.value,
        rule_note=matched.effects.note or effect.note,
        source=worker_source,
        is_crisis=is_crisis,
        client_turn_id=client_turn_id,
    )
    _apply_rule_score(worker, intent)
    worker.marks = [
        {"kind": "hit", "start": 0, "end": min(len(text), 40)}
    ] if matched.hit_words else []

    if is_crisis:
        card = build_crisis_card(text)
        model.crisis_flag = True
        paused = True
        client_turn = None
        suggestion = None
        worker.meta = {
            "emotion_after": emotion_after,
            "used_ai": False,
            "degraded": False,
            "risk_level": risk.value,
            "crisis_card": _card_dict(card),
        }
    else:
        paused = False
        suggestion_card = build_suggestion(
            model.emotion,
            judge_count=sum(1 for item in turns if item.intent == Intent.JUDGEMENT.value),
            hopeless_detected=bool(matched.hit_words),
            last_utterance=text,
        )
        suggestion = _suggestion_out(suggestion_card)
        reply_text = reply or _fallback_reply(emotion_after, base_index, model.scenario_id)
        client_turn = Turn(
            id=uuid.uuid4(),
            session_id=model.id,
            turn_index=base_index + 1,
            speaker=Speaker.CLIENT.value,
            text=reply_text,
            intent=None,
            source="ai" if (reply and worker_source == "ai") else "fallback",
            is_crisis=False,
            meta={
                "emotion_after": emotion_after,
                "used_ai": bool(reply and worker_source == "ai"),
                "degraded": degraded,
                "risk_level": RiskLevel.NONE.value,
            },
        )
        worker.meta = {
            "emotion_after": emotion_after,
            "used_ai": worker_source == "ai",
            "degraded": degraded,
            "risk_level": risk.value,
            "suggestion": suggestion.model_dump() if suggestion else None,
        }

    session.add(worker)
    if client_turn is not None:
        session.add(client_turn)

    model.emotion = emotion_after
    model.turn_count += 1
    model.used_ai = model.used_ai or used_ai
    await session.commit()
    await session.refresh(worker)
    if client_turn is not None:
        await session.refresh(client_turn)

    return TurnPairOut(
        worker=_turn_out(worker),
        client=_turn_out(client_turn) if client_turn is not None else None,
        session=_session_out(model, scenario.name),
        paused=paused,
    )


# ═══════════════════════════════════════════════════════════
# 四、评分与融合
# ═══════════════════════════════════════════════════════════


def _dialogue_messages(turns: list[Turn]) -> list[DialogMessage]:
    return [
        DialogMessage(speaker=Speaker(turn.speaker), text=turn.text, is_crisis=turn.is_crisis)
        for turn in turns
    ]


def _format_dialogue(turns: list[Turn]) -> str:
    lines = []
    for turn in turns:
        role = "学生" if turn.speaker == Speaker.WORKER.value else "角色"
        lines.append(f"{role}：{turn.text}")
    return "\n".join(lines)


def _score_adjust(turns: list[Turn]) -> dict[DimensionKey, int]:
    adjust: dict[DimensionKey, int] = {}
    for turn in turns:
        if not turn.dimension or not turn.delta:
            continue
        key = DimensionKey(turn.dimension)
        adjust[key] = adjust.get(key, 0) + int(turn.delta)
    return adjust


async def _rule_scores(session: AsyncSession, model: TrainingSession, completed_stages: int):
    turns = await _load_turns(session, model.id)
    collected = collect_utterances(_dialogue_messages(turns))
    rule = compute_rule_score(
        RuleScoreInput(
            utterances=collected.utterances,
            hopeless_detected=collected.hopeless_seen,
            hopeless_recognized=collected.hopeless_recognized,
            total_stages=3,
            completed_stages=completed_stages,
            score_adjust=_score_adjust(turns),
            judge_count=collected.judge_count,
            vague_empathy_count=collected.vague_empathy_count,
        )
    )
    return rule, collected, turns


def _weakness_dict(scores: dict[DimensionKey, int]) -> dict[str, Any]:
    report = find_weakness(scores)
    return dataclasses.asdict(report) | {"dimension": report.dimension.value}


def _notes_payload(turns: list[Turn], scores: dict[DimensionKey, int]) -> list[dict[str, Any]]:
    notes = build_margin_notes(
        [
            (index, Speaker(turn.speaker), turn.text, None)
            for index, turn in enumerate(turns)
            if turn.speaker == Speaker.WORKER.value
        ]
    )
    payload: list[dict[str, Any]] = []
    for note in notes:
        payload.append(
            {
                "index": note.index,
                "speaker": note.speaker.value,
                "utterance": note.utterance,
                "response": note.response,
                "dimension": note.dimension.value,
                "delta": note.delta,
                "rule_note": note.rule_note,
                "source": note.source,
                "score": scores.get(note.dimension, 0),
            }
        )
    return payload


async def _upsert_stage_score(
    session: AsyncSession,
    model: TrainingSession,
    *,
    stage_index: int,
    scores: dict[DimensionKey, int],
    total: int,
    source: ScoreSource,
    used_ai: bool,
) -> StageScore:
    row = (
        await session.execute(
            select(StageScore).where(
                StageScore.session_id == model.id,
                StageScore.stage_index == stage_index,
            )
        )
    ).scalar_one_or_none()
    payload = {key.value: int(value) for key, value in scores.items()}
    if row is None:
        row = StageScore(
            id=uuid.uuid4(),
            session_id=model.id,
            stage_index=stage_index,
            scores=payload,
            total=total,
            source=source.value,
            used_ai=used_ai,
        )
        session.add(row)
    else:
        row.scores = payload
        row.total = total
        row.source = source.value
        row.used_ai = used_ai
    return row


async def score_stage(
    session: AsyncSession,
    account: Account,
    session_id: uuid.UUID,
    *,
    stage_index: int,
    gateway: AIGateway,
) -> ScoringOut:
    model = await load_owned_session(session, account, session_id)
    if model.status != SessionStatus.ACTIVE.value:
        raise AppError.conflict("会话已结束，不能继续评分")

    rule_scores, collected, turns = await _rule_scores(session, model, stage_index)
    ai_scores: dict[DimensionKey, int] | None = None
    meta = AiMetaData(False, None, "crisis_blocked" if collected.crisis_seen else "no_key")

    if not collected.crisis_seen and turns:
        score_ctx = ScoreContext(
            dialogue=_format_dialogue(turns),
            stats=ScoreStats(
                worker_turns=collected.worker_turns,
                judge_count=collected.judge_count,
                hopeless_seen=collected.hopeless_seen,
                hopeless_recognized=collected.hopeless_recognized,
                crisis_seen=collected.crisis_seen,
            ),
        )
        parsed, meta = await gateway.score(score_ctx, account_id=account.id)
        if parsed is not None:
            ai_scores = {key: int(value.get("score", 0)) for key, value in parsed.items()}

    merged = merge_scores(rule_scores, ai_scores)
    total = weighted_total(merged.scores)
    SCORE_OVERALL.observe(total)
    source = ScoreSource.BLEND if merged.used_ai else ScoreSource.RULE
    row = await _upsert_stage_score(
        session,
        model,
        stage_index=stage_index,
        scores=merged.scores,
        total=total,
        source=source,
        used_ai=merged.used_ai,
    )
    model.used_ai = model.used_ai or merged.used_ai
    await session.commit()

    return ScoringOut(
        stage_index=stage_index,
        scores={key.value: int(value) for key, value in merged.scores.items()},
        total=total,
        source=source,
        used_ai=merged.used_ai,
        missing=[item.value for item in merged.missing],
        weakness=_weakness_dict(merged.scores),
        margin_notes=_notes_payload(turns, merged.scores),
    )


# ═══════════════════════════════════════════════════════════
# 五、结案与复盘
# ═══════════════════════════════════════════════════════════


def _record_values(record: TrainingRecord, scores: dict[DimensionKey, int]) -> None:
    record.score_empathy = int(scores.get(DimensionKey.EMPATHY, 0))
    record.score_question = int(scores.get(DimensionKey.QUESTION, 0))
    record.score_advice = int(scores.get(DimensionKey.ADVICE, 0))
    record.score_ethics = int(scores.get(DimensionKey.ETHICS, 0))
    record.score_process = int(scores.get(DimensionKey.PROCESS, 0))
    record.score_risk = int(scores.get(DimensionKey.RISK, 0))
    record.score_total = weighted_total(scores)


async def finish_session(
    session: AsyncSession, account: Account, session_id: uuid.UUID
) -> FinishOut:
    model = await load_owned_session(session, account, session_id)
    scenario = await get_scenario(session, model.scenario_id)

    existing = (
        await session.execute(
            select(TrainingRecord).where(TrainingRecord.session_id == model.id)
        )
    ).scalar_one_or_none()

    stage_rows = list(
        (
            await session.execute(
                select(StageScore)
                .where(StageScore.session_id == model.id)
                .order_by(StageScore.stage_index)
            )
        )
        .scalars()
        .all()
    )

    if stage_rows:
        keys = [DimensionKey(key) for key in BASE_SCORES]
        scores = {
            key: int(
                round(
                    sum(int((row.scores or {}).get(key.value, 0)) for row in stage_rows)
                    / len(stage_rows)
                )
            )
            for key in keys
        }
        used_ai = any(row.used_ai for row in stage_rows)
        source = ScoreSource.BLEND if used_ai else ScoreSource.RULE
    else:
        rule, collected, _ = await _rule_scores(session, model, model.ui_phase)
        scores = rule
        used_ai = False
        source = ScoreSource.RULE

    total = weighted_total(scores)
    now = datetime.now(timezone.utc)
    created = model.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    duration = max(0, int((now - created).total_seconds()))

    if existing is None:
        record = TrainingRecord(
            id=uuid.uuid4(),
            owner_id=account.id,
            session_id=model.id,
            scenario_id=model.scenario_id,
            scenario_name=scenario.name,
            difficulty_label=difficulty_label_of(model.difficulty),
            blindfold=model.blindfold,
            ui_phase=model.ui_phase,
            score_source=source.value,
            ai_used=used_ai,
            duration_sec=duration,
        )
        _record_values(record, scores)
        session.add(record)
    else:
        record = existing
        _record_values(record, scores)
        record.score_source = source.value
        record.ai_used = used_ai
        record.duration_sec = duration

    model.status = SessionStatus.FINISHED.value
    model.finished_at = now
    model.total_score = total
    model.used_ai = model.used_ai or used_ai
    await session.commit()
    await session.refresh(record)
    await session.refresh(model)
    TRAINING_COMPLETED.labels(
        model.scenario_id, difficulty_label_of(model.difficulty), "finished"
    ).inc()

    return FinishSchema(
        record_id=record.id,
        session=_session_out(model, scenario.name),
        scores={key.value: int(value) for key, value in scores.items()},
        total=total,
        source=source,
        ai_used=used_ai,
        duration_sec=duration,
    )


def _template_debrief(scores: dict[DimensionKey, int]) -> dict[str, str]:
    report = find_weakness(scores)
    return {
        "strength": "你能完整走完这次面谈，并且始终把注意力放在对方身上，这份稳定本身就是专业性的基础。",
        "improvement": report.advice,
        "next_step": "下一次面谈先做完整的开场与知情同意，再在对方说出情绪词时停三秒，用一句复述接住，而不是马上提问。",
    }


async def debrief_session(
    session: AsyncSession,
    account: Account,
    session_id: uuid.UUID,
    *,
    gateway: AIGateway,
) -> DebriefSchema:
    model = await load_owned_session(session, account, session_id)
    scenario = await get_scenario(session, model.scenario_id)

    existing = (
        await session.execute(select(Debrief).where(Debrief.session_id == model.id))
    ).scalar_one_or_none()
    if existing is not None:
        return DebriefSchema(
            session_id=model.id,
            strength=existing.strength,
            improvement=existing.improvement,
            next_step=existing.next_step,
            used_ai=existing.used_ai,
            model=existing.model,
        )

    record = (
        await session.execute(
            select(TrainingRecord).where(TrainingRecord.session_id == model.id)
        )
    ).scalar_one_or_none()

    if record is not None:
        scores = {
            DimensionKey.EMPATHY: record.score_empathy,
            DimensionKey.QUESTION: record.score_question,
            DimensionKey.ADVICE: record.score_advice,
            DimensionKey.ETHICS: record.score_ethics,
            DimensionKey.PROCESS: record.score_process,
            DimensionKey.RISK: record.score_risk,
        }
        scores_total = record.score_total
    else:
        scores, _collected, _turns = await _rule_scores(session, model, model.ui_phase)
        scores_total = weighted_total(scores)

    turns = await _load_turns(session, model.id)
    hit_rules = [turn.rule_note for turn in turns if turn.rule_note]
    ctx = DebriefContext(
        nickname=account.nickname or "同学",
        name=scenario.name,
        age=scenario.age,
        identity=scenario.archetype,
        scores={key: int(value) for key, value in scores.items()},
        hit_rules=hit_rules[:20],
    )
    sections, meta = await gateway.debrief(ctx, account_id=account.id)
    used_ai = meta.used_ai
    if sections is None:
        sections = _template_debrief(scores)
        used_ai = False

    entry = Debrief(
        id=uuid.uuid4(),
        session_id=model.id,
        strength=str(sections.get("strength", ""))[:320],
        improvement=str(sections.get("improvement", ""))[:320],
        next_step=str(sections.get("next_step", ""))[:320],
        used_ai=used_ai,
        model=meta.model,
        payload={"scores_total": scores_total, "degrade_reason": meta.degrade_reason},
    )
    session.add(entry)
    await session.commit()

    return DebriefSchema(
        session_id=model.id,
        strength=entry.strength,
        improvement=entry.improvement,
        next_step=entry.next_step,
        used_ai=used_ai,
        model=meta.model,
    )


async def delete_session(session: AsyncSession, account: Account, session_id: uuid.UUID) -> None:
    """软删除用：直接物理删除仅用于测试清理，正式环境走 aborted 状态。"""
    model = await load_owned_session(session, account, session_id)
    await session.execute(delete(Turn).where(Turn.session_id == model.id))
    await session.delete(model)
    await session.commit()

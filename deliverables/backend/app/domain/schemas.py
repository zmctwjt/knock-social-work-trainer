"""Pydantic v2 请求/响应模型（API 契约的唯一来源）。

分层约定：
- 请求模型只做格式与长度校验，业务规则（状态机、越权、配额）放服务层；
- 响应模型不回声任何凭据字段；
- 所有对外响应经 `Envelope` 包裹，`code=0` 表示成功。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    DIMENSION_ORDER,
    Difficulty,
    DimensionKey,
    Intent,
    RiskLevel,
    Role,
    ScoreSource,
    SessionStatus,
    Speaker,
)

DataT = TypeVar("DataT")


# ═══════════════════════════════════════════════════════════
# 一、统一响应包
# ═══════════════════════════════════════════════════════════


class Envelope(BaseModel, Generic[DataT]):
    code: int = 0
    message: str = "ok"
    data: DataT | None = None
    request_id: str = ""


class MessageOut(BaseModel):
    message: str = "ok"


# ═══════════════════════════════════════════════════════════
# 二、认证
# ═══════════════════════════════════════════════════════════


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=4096)


class GuestRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=32)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: Role
    is_guest: bool = False


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    nickname: str
    role: Role
    is_guest: bool
    created_at: datetime


class LoginOut(BaseModel):
    account: AccountOut
    tokens: TokenPair


class GuestOut(BaseModel):
    account: AccountOut
    tokens: TokenPair
    notice: str = "游客账号为只读体验，24 小时后失效；创建训练请使用正式账号。"


# ═══════════════════════════════════════════════════════════
# 三、案例与知识卡
# ═══════════════════════════════════════════════════════════


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    age: int
    gender: str
    archetype: str
    difficulty: int
    difficulty_label: str
    resistance: int
    sensitive_tag: str | None = None
    brief: str
    initial_emotion: int
    active: bool = True


class ScenarioListOut(BaseModel):
    items: list[ScenarioOut]
    total: int


class KnowledgeCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: str
    summary: str
    content: str
    tags: list[str] = Field(default_factory=list)
    stage: int | None = None


class KnowledgeCardListOut(BaseModel):
    items: list[KnowledgeCardOut]
    total: int


# ═══════════════════════════════════════════════════════════
# 四、训练会话
# ═══════════════════════════════════════════════════════════


class SessionCreateRequest(BaseModel):
    scenario_id: str = Field(min_length=2, max_length=16)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    blindfold: bool = False
    max_turns: int = Field(default=40, ge=4, le=200)
    client_session_id: str | None = Field(default=None, max_length=64)


class SessionOut(BaseModel):
    id: uuid.UUID
    scenario_id: str
    scenario_name: str
    status: SessionStatus
    difficulty: int
    difficulty_label: str
    blindfold: bool
    ui_phase: int
    emotion: int
    turn_count: int
    max_turns: int
    crisis_flag: bool
    total_score: int | None = None
    used_ai: bool
    created_at: datetime
    finished_at: datetime | None = None


class SessionListOut(BaseModel):
    items: list[SessionOut]
    total: int


class TurnCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    client_turn_id: str | None = Field(default=None, max_length=64)
    stage: int | None = Field(default=None, ge=1, le=3)

    @field_validator("text")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("发言内容不能为空")
        return cleaned


class ProofMarkOut(BaseModel):
    kind: str
    start: int
    end: int


class SuggestionOut(BaseModel):
    title: str
    quote: str
    basis: str


class CrisisHotlineOut(BaseModel):
    code: str
    label: str


class CrisisCardOut(BaseModel):
    level: str
    title: str
    principles: list[str]
    hotlines: list[CrisisHotlineOut]
    citation: str
    disclaimer: str


class TurnOut(BaseModel):
    id: uuid.UUID
    turn_index: int
    speaker: Speaker
    text: str
    intent: Intent | None = None
    dimension: DimensionKey | None = None
    delta: int = 0
    rule_note: str = ""
    source: str = "rule"
    marks: list[ProofMarkOut] = Field(default_factory=list)
    is_crisis: bool = False
    emotion_after: int
    used_ai: bool = False
    degraded: bool = False
    suggestion: SuggestionOut | None = None
    crisis_card: CrisisCardOut | None = None
    risk_level: RiskLevel = RiskLevel.NONE


class TurnPairOut(BaseModel):
    """一次发言的完整结果：学生这句 + 角色回应（危机时回应为空）。"""

    worker: TurnOut
    client: TurnOut | None = None
    session: SessionOut
    paused: bool = False


class StageScoreOut(BaseModel):
    stage_index: int
    scores: dict[str, int]
    total: int
    source: ScoreSource
    used_ai: bool
    weakness: dict[str, Any] | None = None


class SessionDetailOut(BaseModel):
    session: SessionOut
    turns: list[TurnOut]
    stage_scores: list[StageScoreOut]


class ScoringOut(BaseModel):
    stage_index: int
    scores: dict[str, int]
    total: int
    source: ScoreSource
    used_ai: bool
    missing: list[str] = Field(default_factory=list)
    weakness: dict[str, Any] | None = None
    margin_notes: list[dict[str, Any]] = Field(default_factory=list)


class FinishOut(BaseModel):
    record_id: uuid.UUID
    session: SessionOut
    scores: dict[str, int]
    total: int
    source: ScoreSource
    ai_used: bool
    duration_sec: int


class DebriefOut(BaseModel):
    session_id: uuid.UUID
    strength: str
    improvement: str
    next_step: str
    used_ai: bool
    model: str | None = None


# ═══════════════════════════════════════════════════════════
# 五、统计
# ═══════════════════════════════════════════════════════════


class DimensionAverage(BaseModel):
    key: DimensionKey
    name: str
    average: float


class RecentRecordOut(BaseModel):
    id: uuid.UUID
    scenario_id: str
    scenario_name: str
    score_total: int
    created_at: datetime


class StatsMeOut(BaseModel):
    account_id: uuid.UUID
    total_sessions: int
    total_turns: int
    avg_total: float
    best_total: int
    active_days: int
    streak_days: int
    dimensions: list[DimensionAverage]
    recent: list[RecentRecordOut]


class HeatmapDayOut(BaseModel):
    date: str
    count: int
    level: int


class HeatmapOut(BaseModel):
    days: list[HeatmapDayOut]
    max_count: int
    total: int


# ═══════════════════════════════════════════════════════════
# 六、AI 链路（v1）
# ═══════════════════════════════════════════════════════════


class AiMeta(BaseModel):
    used_ai: bool
    model: str | None = None
    degrade_reason: str | None = None
    latency_ms: int = 0
    cache_hit: bool = False


class IntentRequest(BaseModel):
    input: str = Field(min_length=1, max_length=2000)
    stage: str | None = Field(default=None, max_length=32)
    scenario_id: str | None = Field(default=None, max_length=16)
    session_id: uuid.UUID | None = None


class IntentOut(BaseModel):
    intent: Intent
    rule_hint: Intent | None = None
    source: str = "ai"
    meta: AiMeta


class PersonaMessage(BaseModel):
    role: Literal["worker", "client", "system"] = "worker"
    text: str = Field(min_length=1, max_length=2000)


class PersonaRequest(BaseModel):
    scenario_id: str = Field(min_length=2, max_length=16)
    emotion: int = Field(default=50, ge=0, le=100)
    history: list[PersonaMessage] = Field(default_factory=list, max_length=80)
    said_lines: list[str] = Field(default_factory=list, max_length=40)
    phase: int | None = Field(default=None, ge=1, le=3)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    session_id: uuid.UUID | None = None


class PersonaOut(BaseModel):
    text: str
    meta: AiMeta


class ScoreRequest(BaseModel):
    dialogue: list[PersonaMessage] = Field(default_factory=list, max_length=200)
    session_id: uuid.UUID | None = None
    stage_index: int = Field(default=1, ge=1, le=3)
    completed_stages: int = Field(default=0, ge=0, le=3)
    total_stages: int = Field(default=3, ge=1, le=3)


class ScoreOut(BaseModel):
    scores: dict[str, int]
    total: int
    source: ScoreSource
    used_ai: bool
    missing: list[str] = Field(default_factory=list)
    meta: AiMeta


class DebriefRequest(BaseModel):
    session_id: uuid.UUID | None = None
    scores: dict[str, int] = Field(default_factory=dict)
    hit_rules: list[str] = Field(default_factory=list, max_length=50)
    nickname: str = Field(default="同学", max_length=32)


class DebriefSectionsOut(BaseModel):
    strength: str
    improvement: str
    next_step: str
    meta: AiMeta


# ═══════════════════════════════════════════════════════════
# 七、健康与运维
# ═══════════════════════════════════════════════════════════


class HealthOut(BaseModel):
    ok: bool = True
    status: str = "ok"
    version: str
    environment: str
    uptime_sec: int
    pid: int


class ReadyCheck(BaseModel):
    name: str
    ready: bool
    detail: str = ""


class ReadyOut(BaseModel):
    ok: bool
    status: str
    checks: list[ReadyCheck]
    ai_configured: bool
    model_chain: list[str] = Field(default_factory=list)


class UsageOut(BaseModel):
    calls: int = 0
    ok: int = 0
    failed: int = 0
    degraded: int = 0
    cache_hits: int = 0
    by_function: dict[str, int] = Field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    daily_cap: int = 800
    rpm_per_ip: int = 20
    concurrency: int = 2


def difficulty_label_of(difficulty: int) -> str:
    return {
        1: Difficulty.EASY.value,
        2: Difficulty.EASY.value,
        3: Difficulty.STANDARD.value,
        4: Difficulty.CHALLENGE.value,
        5: Difficulty.CHALLENGE.value,
    }.get(difficulty, Difficulty.STANDARD.value)


def scores_by_key(raw: dict[str, Any]) -> dict[str, int]:
    """把任意来源的六维分数规范成 {key: int}，缺项按 0 补齐。"""
    cleaned: dict[str, int] = {}
    for key in DIMENSION_ORDER:
        try:
            value = int(round(float(raw.get(key.value, 0))))
        except (TypeError, ValueError):
            value = 0
        cleaned[key.value] = max(0, min(100, value))
    return cleaned


# ═══════════════════════════════════════════════════════════
# 十五、多角色能力（教师端 / 管理员端）
# ═══════════════════════════════════════════════════════════


class AccountAdminOut(AccountOut):
    """管理员视角的账号：额外暴露启用状态、归属教师与最近登录。"""

    is_active: bool = True
    teacher_id: uuid.UUID | None = None
    last_login_at: datetime | None = None


class AccountListOut(BaseModel):
    items: list[AccountAdminOut] = Field(default_factory=list)
    total: int = 0


class AccountCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    role: Literal["student", "teacher", "admin"] = "student"

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class AccountActiveRequest(BaseModel):
    active: bool


class LearnerRecordOut(BaseModel):
    """教师视角的学员条目。

    两用：课表格子（sessions/avg_total 汇总）与单条训练记录（带 scenario_name 等）。
    """

    account_id: uuid.UUID
    username: str
    nickname: str
    sessions: int = 0
    avg_total: float = 0.0
    is_active: bool = True
    last_login_at: datetime | None = None
    scenario_name: str | None = None
    score_total: int | None = None
    created_at: datetime | None = None


class LearnerListOut(BaseModel):
    items: list[LearnerRecordOut] = Field(default_factory=list)
    total: int = 0


class ClassStatsOut(BaseModel):
    learners: int = 0
    sessions: int = 0
    avg_total: float = 0.0
    dimensions: dict[str, float] = Field(default_factory=dict)
    weakest: str = ""
    weakest_score: float = 0.0


class BindLearnerRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class ScenarioUpsertRequest(BaseModel):
    """案例新建/编辑。`id` 在主键上，编辑时按它定位。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=2, max_length=16)
    name: str | None = Field(default=None, max_length=64)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=8)
    archetype: str | None = Field(default=None, max_length=64)
    resistance: int | None = Field(default=None, ge=1, le=5)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    sensitive_tag: str | None = Field(default=None, max_length=64)
    brief: str | None = Field(default=None, max_length=4000)
    initial_emotion: int | None = Field(default=None, ge=0, le=100)
    system_prompt: str | None = Field(default=None, max_length=8000)
    voice_low: str | None = Field(default=None, max_length=2000)
    voice_mid: str | None = Field(default=None, max_length=2000)
    voice_high: str | None = Field(default=None, max_length=2000)
    forbidden: list[str] | None = Field(default=None, max_length=20)
    active: bool | None = None

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CardUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=2, max_length=16)
    title: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=32)
    summary: str | None = Field(default=None, max_length=4000)
    content: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = Field(default=None, max_length=20)
    stage: int | None = Field(default=None, ge=1, le=5)
    order_index: int | None = Field(default=None, ge=0, le=999)


class AdminOverviewOut(BaseModel):
    accounts: int = 0
    teachers: int = 0
    sessions: int = 0
    records: int = 0
    ai_calls_24h: int = 0
    ai_configured: bool = False
    model_chain: list[str] = Field(default_factory=list)
    daily_cap: int = 0
    environment: str = ""


class RuleWordIn(BaseModel):
    group: str = Field(min_length=2, max_length=32)
    word: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=200)


class RuleWordOut(BaseModel):
    group: str
    word: str
    effective: int = 0


class RuleWordsAdminOut(BaseModel):
    groups: list[dict[str, Any]] = Field(default_factory=list)
    custom: list[dict[str, Any]] = Field(default_factory=list)
    loaded_at: str | None = None


class ScriptLineIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    emotion_bucket: Literal["low", "mid", "high"] = "mid"
    scenario_id: str | None = Field(default=None, max_length=16)
    order_index: int = Field(default=0, ge=0, le=999)


class ScriptLinePatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    emotion_bucket: Literal["low", "mid", "high"] | None = None
    order_index: int | None = Field(default=None, ge=0, le=999)
    active: bool | None = None


# ═══════════════════════════════════════════════════════════
# 十六、教师端 / 管理端扩展视图
# ═══════════════════════════════════════════════════════════


class DimensionAvgOut(BaseModel):
    key: str
    name: str
    avg: float = 0.0
    count: int = 0


class TrendPointOut(BaseModel):
    date: str
    sessions: int = 0
    avg_total: float = 0.0


class ScenarioUsageOut(BaseModel):
    scenario_id: str
    scenario_name: str
    sessions: int = 0
    avg_total: float = 0.0


class LearnerDetailOut(BaseModel):
    account_id: uuid.UUID
    username: str
    nickname: str
    is_active: bool = True
    last_login_at: datetime | None = None
    sessions: int = 0
    finished: int = 0
    avg_total: float = 0.0
    best_total: int = 0
    total_turns: int = 0
    total_minutes: int = 0
    dimensions: list[DimensionAvgOut] = Field(default_factory=list)
    weakest: str = ""
    trend: list[TrendPointOut] = Field(default_factory=list)
    scenarios: list[ScenarioUsageOut] = Field(default_factory=list)


class ClassTrendOut(BaseModel):
    points: list[TrendPointOut] = Field(default_factory=list)
    dimensions: list[DimensionAvgOut] = Field(default_factory=list)
    scenarios: list[ScenarioUsageOut] = Field(default_factory=list)


class AdminTrendOut(BaseModel):
    days: int = 30
    points: list[TrendPointOut] = Field(default_factory=list)
    role_distribution: dict[str, int] = Field(default_factory=dict)
    scenario_usage: list[ScenarioUsageOut] = Field(default_factory=list)
    dimensions: list[DimensionAvgOut] = Field(default_factory=list)


class AiLogQuery(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    purpose: str | None = None
    status: str | None = None


class AiLogItemOut(BaseModel):
    id: str
    purpose: str
    status: str
    model: str
    latency_ms: int = 0
    degrade_reason: str | None = None
    used_ai: bool = False
    cache_hit: bool = False
    created_at: str | None = None


class AiLogListOut(BaseModel):
    items: list[AiLogItemOut] = Field(default_factory=list)
    total: int = 0
    success_rate: float = 0.0
    avg_latency_ms: int = 0


class BulkActiveRequest(BaseModel):
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    active: bool


class BulkResultOut(BaseModel):
    updated: int = 0
    failed: int = 0
    messages: list[str] = Field(default_factory=list)

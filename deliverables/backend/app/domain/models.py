"""SQLAlchemy 2.0 ORM 模型（11 张表）。

与原 Supabase 模型的映射关系见 `deliverables/docs/06_数据库设计与迁移.md`：
`training_records` / `training_details` / `proficiency` / `session_record`
四张表的职责被拆成 `training_sessions` / `turns` / `stage_scores` /
`training_records` 三张表加一个会话状态机，原因是原表用 jsonb 存整段对话，
既无法分页查询也无法做行级授权。

约定：
- 主键统一 UUID（SQLite 以 CHAR(32) 存储，PG 用原生 UUID）；
- 枚举以字符串落库，取值由 `app.domain.enums` 定义，读写经服务层转换；
- 所有业务表带 `created_at`，可变表带 `updated_at`；
- 授权不依赖数据库 RLS，而由应用层 `where(owner_id == ...)` 强制过滤。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ═══════════════════════════════════════════════════════════
# 一、账号与凭证
# ═══════════════════════════════════════════════════════════


class Account(Base, TimestampMixin):
    """账号表。密码只存 Argon2id 摘要，任何接口都不回传密码字段。"""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 学员归属教师（简易班级归属；二期换独立班级实体与外键）
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["TrainingSession"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="owner", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        Index("ix_accounts_role", "role"),
        Index("ix_accounts_created_at", "created_at"),
        Index("ix_accounts_teacher", "teacher_id"),
    )


class TokenRevocation(Base):
    """JWT 撤销黑名单。登出或改密时把 jti 写进来，校验时查一次。"""

    __tablename__ = "token_revocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    token_type: Mapped[str] = mapped_column(String(20), nullable=False, default="refresh")
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="logout")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (Index("ix_token_revocations_expires_at", "expires_at"),)


class UserSettings(Base, TimestampMixin):
    """用户偏好。字段刻意做成 JSON：偏好项会随前端迭代增加，不值得为每项加列。"""

    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    prefs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # 历史库的 user_settings 缺少 ai_mode 列，而前端早已按该列写云端配置，
    # 导致配置写入必然失败；新库显式补列，默认 hybrid（规则主干 + AI 长尾）。
    # v1 仅落库与回读，不参与四条链路的实时路由，按用户切换属二期能力。
    ai_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="hybrid")

    owner: Mapped[Account] = relationship(back_populates="settings")

    __table_args__ = (Index("ix_user_settings_owner_id", "owner_id"),)


# ═══════════════════════════════════════════════════════════
# 二、内容：案例剧本与知识卡
# ═══════════════════════════════════════════════════════════


class Scenario(Base, TimestampMixin):
    """案例剧本（原 `case_scripts`）。`id` 沿用 W-01 这类业务可读编号。"""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False)
    archetype: Mapped[str] = mapped_column(String(64), nullable=False)
    resistance: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    sensitive_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    initial_emotion: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    voice_low: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_mid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_high: Mapped[str] = mapped_column(Text, nullable=False, default="")
    forbidden: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_scenarios_active_difficulty", "active", "difficulty"),
        Index("ix_scenarios_archetype", "archetype"),
    )

    def voice_for(self, emotion: int) -> str:
        if emotion < 35:
            return self.voice_low
        if emotion <= 60:
            return self.voice_mid
        return self.voice_high


class KnowledgeCard(Base, TimestampMixin):
    """技巧卡（T-01…T-19）与伦理守则。"""

    __tablename__ = "knowledge_cards"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="技巧")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_knowledge_cards_category_order", "category", "order_index"),)


# ═══════════════════════════════════════════════════════════
# 三、训练会话：会话 → 轮次 → 阶段分 → 复盘 → 训练记录
# ═══════════════════════════════════════════════════════════


class TrainingSession(Base, TimestampMixin):
    """一次面谈训练。状态机：active → finished → scored（详见 05 章）。"""

    __tablename__ = "training_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    blindfold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ui_phase: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    emotion: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    crisis_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: 前端生成的会话幂等键，重复提交不会创建第二个会话
    client_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    owner: Mapped[Account] = relationship(back_populates="sessions")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    stage_scores: Mapped[list["StageScore"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    debrief: Mapped["Debrief | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    record: Mapped["TrainingRecord | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "client_session_id", name="uq_sessions_owner_client"),
        Index("ix_sessions_owner_status", "owner_id", "status"),
        Index("ix_sessions_owner_created", "owner_id", "created_at"),
        Index("ix_sessions_scenario_id", "scenario_id"),
    )


class Turn(Base, TimestampMixin):
    """一轮对话。`client_turn_id` 唯一约束是幂等的最后一道防线。"""

    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_note: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="rule")
    marks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    is_crisis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    client_turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    session: Mapped[TrainingSession] = relationship(back_populates="turns")

    __table_args__ = (
        UniqueConstraint("session_id", "turn_index", name="uq_turns_session_index"),
        UniqueConstraint("session_id", "client_turn_id", name="uq_turns_session_client"),
        Index("ix_turns_session_index", "session_id", "turn_index"),
    )


class StageScore(Base, TimestampMixin):
    """阶段评分。每阶段一次，`(session_id, stage_index)` 唯一保证重算幂等。"""

    __tablename__ = "stage_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="rule")
    used_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    session: Mapped[TrainingSession] = relationship(back_populates="stage_scores")

    __table_args__ = (
        UniqueConstraint("session_id", "stage_index", name="uq_stage_scores_session_stage"),
        Index("ix_stage_scores_session", "session_id"),
    )


class Debrief(Base):
    """复盘报告。一段会话只有一份，重复请求直接返回已存结果。"""

    __tablename__ = "debriefs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    strength: Mapped[str] = mapped_column(Text, nullable=False, default="")
    improvement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    used_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    session: Mapped[TrainingSession] = relationship(back_populates="debrief")


class TrainingRecord(Base):
    """训练记录（原 `training_records`）。统计与热力图都读这张表。"""

    __tablename__ = "training_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    scenario_id: Mapped[str] = mapped_column(String(16), nullable=False)
    scenario_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    difficulty_label: Mapped[str] = mapped_column(String(16), nullable=False, default="标准实训")
    blindfold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ui_phase: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    score_empathy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_question: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_advice: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_ethics: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_process: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_risk: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_source: Mapped[str] = mapped_column(String(16), nullable=False, default="blend")
    ai_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    session: Mapped[TrainingSession] = relationship(back_populates="record")

    __table_args__ = (
        Index("ix_records_owner_created", "owner_id", "created_at"),
        Index("ix_records_owner_scenario", "owner_id", "scenario_id"),
        Index("ix_records_score_total", "score_total"),
    )


# ═══════════════════════════════════════════════════════════
# 四、AI 审计
# ═══════════════════════════════════════════════════════════


class AiAuditLog(Base):
    """AI 调用审计。合规底线：不落对话原文，只落 hash 与长度。"""

    __tablename__ = "ai_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="zhipu")
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    used_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    degrade_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_ai_audit_created_at", "created_at"),
        Index("ix_ai_audit_account", "account_id", "created_at"),
        Index("ix_ai_audit_purpose_status", "purpose", "status"),
    )


# ═══════════════════════════════════════════════════════════
# 五、判定词表的运行时覆盖（基线在代码里，见 rule_word_service）
# ═══════════════════════════════════════════════════════════


class RuleWord(Base, TimestampMixin):
    """词表增量与禁用记录。

    基线 162 条仍写在 `app/domain/rules.py`，本表只存"加了什么、禁了什么"，
    因此库清空也不影响判定可用性与危机拦截。`is_baseline` 用于区分
    "被禁用的基线词"与"自定义新词"，前者不可删除、后者可删除。
    """

    __tablename__ = "rule_words"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group: Mapped[str] = mapped_column(String(32), nullable=False)
    word: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("group", "word", name="uq_rule_words_group_word"),
        Index("ix_rule_words_group_enabled", "group", "enabled"),
    )


# ═══════════════════════════════════════════════════════════
# 六、台词节点（任务书"内容维护：维护台词节点"）
# ═══════════════════════════════════════════════════════════


class ScriptLine(Base, TimestampMixin):
    """可维护的服务对象台词。

    基线台词仍是 `session_service.FALLBACK_REPLIES` 里的三档常量，
    保证库不可用时对话照常推进；本表存管理端新增的台词，按
    (情绪档, 排序) 取用，覆盖基线的轮转顺序。`scenario_id` 为空表示
    全角色通用，非空则只对该角色生效。
    """

    __tablename__ = "script_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=True
    )
    emotion_bucket: Mapped[str] = mapped_column(String(8), nullable=False, default="mid")
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_script_lines_bucket_order", "emotion_bucket", "order_index"),
        Index("ix_script_lines_scenario", "scenario_id"),
    )


class TeacherComment(Base, TimestampMixin):
    """教师对某次训练记录的点评。

    为什么要挂在 `TrainingRecord` 而不是 `TrainingSession`：
    学生看的是"这次训练拿了多少分"，点评要跟着成绩一起出现，
    而成绩是结算后写入 `training_records` 的。挂 session 会导致
    "训练还没结算就没有记录可点评"的空档。

    一个记录允许多条点评（同一教师可追加，不同教师也可各评各的），
    所以不做唯一约束，靠 `teacher_id + record_id + created_at` 排序展示。
    """

    __tablename__ = "teacher_comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 点评者（教师或管理员）
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 被点评的学员，冗余存一份便于"按学员查所有点评"而不必join记录表
    learner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 教师给的建议等级：good=表现良好 / watch=需关注 / urgent=需干预
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="good")
    # 是否已读（学生端可提示"老师有新点评"）
    read_by_learner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

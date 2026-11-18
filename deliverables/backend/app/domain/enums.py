"""领域枚举。

意图使用中文取值（与前端、提示词、数据库列保持同一口径），
枚举成员名用英文以便代码检索。
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    GUEST = "guest"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    GUEST = "guest"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    FINISHED = "finished"
    ABORTED = "aborted"


class Speaker(StrEnum):
    WORKER = "worker"
    CLIENT = "client"
    SYSTEM = "system"


class RiskLevel(StrEnum):
    NONE = "none"
    HOPELESSNESS = "hopelessness"
    SUICIDAL = "suicidal"


class Intent(StrEnum):
    EMPATHY = "共情"
    OPEN_QUESTION = "开放提问"
    CLOSED_QUESTION = "封闭提问"
    JUDGEMENT = "评判"
    PREMATURE_ADVICE = "建议过早"
    SILENCE = "沉默陪伴"
    OFF_TOPIC = "离题"
    CRISIS = "危机"


class DimensionKey(StrEnum):
    EMPATHY = "empathy"
    QUESTION = "question"
    ADVICE = "advice"
    ETHICS = "ethics"
    PROCESS = "process"
    RISK = "risk"


class Difficulty(StrEnum):
    EASY = "简单实习"
    STANDARD = "标准实训"
    CHALLENGE = "挑战督导"


class AiMode(StrEnum):
    RULE = "rule"
    HYBRID = "hybrid"
    AI = "ai"


class ScoreSource(StrEnum):
    RULE = "rule"
    AI = "ai"
    BLEND = "blend"


class AICallStatus(StrEnum):
    """AI 审计状态。"""

    OK = "ok"
    CACHED = "cached"
    DEGRADED = "degraded"
    ERROR = "error"


class DegradeReason(StrEnum):
    """降级原因（同时作为 Prometheus `ai_degraded_total{reason}` 的标签值）。"""

    NOT_CONFIGURED = "not_configured"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_5XX = "upstream_5xx"
    BAD_OUTPUT = "bad_output"
    BREAKER_OPEN = "breaker_open"
    QUOTA_EXHAUSTED = "quota_exhausted"
    CRISIS_BLOCKED = "crisis_blocked"
    NETWORK = "network"
    AUTH_ERROR = "auth_error"


#: 六维顺序（与评分、雷达图、数据库列顺序一致）
DIMENSION_ORDER: tuple[DimensionKey, ...] = (
    DimensionKey.EMPATHY,
    DimensionKey.QUESTION,
    DimensionKey.ADVICE,
    DimensionKey.ETHICS,
    DimensionKey.PROCESS,
    DimensionKey.RISK,
)

INTENT_ORDER: tuple[Intent, ...] = (
    Intent.EMPATHY,
    Intent.OPEN_QUESTION,
    Intent.CLOSED_QUESTION,
    Intent.JUDGEMENT,
    Intent.PREMATURE_ADVICE,
    Intent.SILENCE,
    Intent.OFF_TOPIC,
    Intent.CRISIS,
)

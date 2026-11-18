"""AI 审计落库（脱敏）。

四件事必须记：谁（account_id）、调了什么（purpose/model/prompt_version）、
结果如何（status/degrade_reason/latency/tokens）、输入指纹（hash + 长度）。
**不记录对话原文**：输入只留 sha256 前 16 位与字符长度，既可用于关联排查，
又不会把服务对象的原话落进日志表——这是社工场景的红线之一。

写入失败只降级为 debug 日志，绝不影响主流程：审计是旁路，不是依赖。
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.domain.models import AiAuditLog

logger = get_logger(__name__)


def fingerprint(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


class AuditRecorder:
    """持有独立的会话工厂：审计写入不应与业务事务同生共死。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def record(
        self,
        *,
        purpose: str,
        provider: str,
        model: str | None,
        status: str,
        used_ai: bool,
        degrade_reason: str | None,
        prompt_version: str,
        input_text: str = "",
        output_text: str = "",
        latency_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cache_hit: bool = False,
        account_id: uuid.UUID | None = None,
        request_id: str = "-",
    ) -> None:
        entry = AiAuditLog(
            request_id=request_id,
            account_id=account_id,
            purpose=purpose,
            provider=provider,
            model=model,
            status=status,
            used_ai=used_ai,
            degrade_reason=degrade_reason,
            prompt_version=prompt_version,
            input_hash=fingerprint(input_text),
            input_len=len(input_text or ""),
            output_len=len(output_text or ""),
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cache_hit=cache_hit,
        )
        try:
            async with self.session_factory() as session:
                session.add(entry)
                await session.commit()
        except Exception:  # noqa: BLE001 —— 审计失败不得冒泡
            logger.debug("ai_audit_write_failed", exc_info=True)

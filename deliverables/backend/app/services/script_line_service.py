"""台词节点覆盖层（任务书"内容维护：维护台词节点"）。

与词表覆盖层同构：
- 基线台词是 `session_service.FALLBACK_REPLIES`（情绪三档各若干句），
  库不可用时对话仍能推进；
- 数据库只存管理端新增的台词（`script_lines`），启动时加载成内存快照；
- 取用时"库里有就用库里的，没有就回落到基线"，避免维护动作把对话搞空。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.models import Scenario, ScriptLine

BUCKETS = ("low", "mid", "high")
BUCKET_LABELS = {"low": "低情绪", "mid": "中情绪", "high": "高情绪"}


class ScriptLineOverlay:
    """内存快照：{scenario_id 或 "": {bucket: [text, ...]}}。"""

    def __init__(self) -> None:
        self._by_key: dict[str, dict[str, list[str]]] = {}

    async def reload(self, session: AsyncSession) -> int:
        rows = (
            await session.execute(
                select(ScriptLine)
                .where(ScriptLine.active.is_(True))
                .order_by(ScriptLine.order_index, ScriptLine.created_at)
            )
        ).scalars().all()
        data: dict[str, dict[str, list[str]]] = {}
        for row in rows:
            key = row.scenario_id or ""
            data.setdefault(key, {}).setdefault(row.emotion_bucket, []).append(row.text)
        self._by_key = data
        return len(rows)

    def lines_for(self, scenario_id: str, bucket: str) -> list[str]:
        """优先取角色专属，其次通用；都没有返回空表示回落基线。"""
        return list(
            self._by_key.get(scenario_id, {}).get(bucket)
            or self._by_key.get("", {}).get(bucket)
            or []
        )

    def counts(self) -> dict[str, int]:
        return {k or "通用": sum(len(v) for v in buckets.values()) for k, buckets in self._by_key.items()}


OVERLAY = ScriptLineOverlay()


# ── 管理端维护动作 ──────────────────────────────────────────
async def list_lines(session: AsyncSession, scenario_id: str | None = None) -> dict[str, object]:
    stmt = select(ScriptLine).order_by(ScriptLine.order_index, ScriptLine.created_at)
    if scenario_id:
        stmt = stmt.where(ScriptLine.scenario_id == scenario_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "scenario_id": r.scenario_id,
                "emotion_bucket": r.emotion_bucket,
                "bucket_label": BUCKET_LABELS.get(r.emotion_bucket, r.emotion_bucket),
                "text": r.text,
                "order_index": r.order_index,
                "active": r.active,
            }
            for r in rows
        ],
        "buckets": [{"value": b, "label": BUCKET_LABELS[b]} for b in BUCKETS],
        "overlay_counts": OVERLAY.counts(),
    }


async def create_line(
    session: AsyncSession,
    *,
    text: str,
    emotion_bucket: str = "mid",
    scenario_id: str | None = None,
    order_index: int = 0,
) -> dict[str, object]:
    cleaned = text.strip()
    if not cleaned:
        raise AppError.bad_request("台词内容不能为空")
    if emotion_bucket not in BUCKETS:
        raise AppError.bad_request(f"情绪档只能是 {'/'.join(BUCKETS)}")
    if scenario_id:
        exists = await session.get(Scenario, scenario_id)
        if exists is None:
            raise AppError.not_found("案例不存在")
    row = ScriptLine(
        id=uuid.uuid4(),
        scenario_id=scenario_id or None,
        emotion_bucket=emotion_bucket,
        text=cleaned[:500],
        order_index=order_index,
        active=True,
    )
    session.add(row)
    await session.commit()
    await OVERLAY.reload(session)
    return {"id": str(row.id), "text": row.text, "emotion_bucket": row.emotion_bucket}


async def update_line(
    session: AsyncSession,
    line_id: uuid.UUID,
    *,
    text: str | None = None,
    emotion_bucket: str | None = None,
    order_index: int | None = None,
    active: bool | None = None,
) -> dict[str, object]:
    row = await session.get(ScriptLine, line_id)
    if row is None:
        raise AppError.not_found("台词不存在")
    if text is not None:
        cleaned = text.strip()
        if not cleaned:
            raise AppError.bad_request("台词内容不能为空")
        row.text = cleaned[:500]
    if emotion_bucket is not None:
        if emotion_bucket not in BUCKETS:
            raise AppError.bad_request(f"情绪档只能是 {'/'.join(BUCKETS)}")
        row.emotion_bucket = emotion_bucket
    if order_index is not None:
        row.order_index = order_index
    if active is not None:
        row.active = active
    await session.commit()
    await OVERLAY.reload(session)
    return {"id": str(row.id), "text": row.text, "active": row.active}


async def delete_line(session: AsyncSession, line_id: uuid.UUID) -> dict[str, object]:
    row = await session.get(ScriptLine, line_id)
    if row is None:
        raise AppError.not_found("台词不存在")
    await session.delete(row)
    await session.commit()
    await OVERLAY.reload(session)
    return {"id": str(line_id), "deleted": True}


__all__ = [
    "BUCKETS",
    "BUCKET_LABELS",
    "OVERLAY",
    "ScriptLineOverlay",
    "create_line",
    "delete_line",
    "list_lines",
    "update_line",
]

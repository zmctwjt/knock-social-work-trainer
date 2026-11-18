"""统计服务：个人看板与训练热力图。

数据来源只有 `training_records`（结案快照）与 `turns`（细粒度发言），
不依赖物化视图——原 Supabase 的两个视图在新模型里退化成两条聚合查询，
换来的是"一处写入、随时可算"的简单性。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DimensionKey
from app.domain.models import Account, TrainingRecord, TrainingSession, Turn
from app.domain.schemas import (
    DimensionAverage,
    HeatmapDayOut,
    HeatmapOut,
    RecentRecordOut,
    StatsMeOut,
)
from app.domain.scoring import DIMENSIONS

DIMENSION_COLUMNS = {
    DimensionKey.EMPATHY: "score_empathy",
    DimensionKey.QUESTION: "score_question",
    DimensionKey.ADVICE: "score_advice",
    DimensionKey.ETHICS: "score_ethics",
    DimensionKey.PROCESS: "score_process",
    DimensionKey.RISK: "score_risk",
}


def _as_date(moment: datetime) -> date:
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.date()


def _streak(days: set[date]) -> int:
    if not days:
        return 0
    cursor = max(days)
    today = datetime.now(timezone.utc).date()
    # 今天还没练不算断签：从最近一次训练日往前数
    if cursor < today - timedelta(days=1):
        return 0
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def me(session: AsyncSession, account: Account) -> StatsMeOut:
    rows = list(
        (
            await session.execute(
                select(TrainingRecord)
                .where(TrainingRecord.owner_id == account.id)
                .order_by(TrainingRecord.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    total_turns = (
        await session.execute(
            select(func.count(Turn.id))
            .select_from(Turn)
            .join(TrainingSession, TrainingSession.id == Turn.session_id)
            .where(TrainingSession.owner_id == account.id)
        )
    ).scalar_one()

    if not rows:
        return StatsMeOut(
            account_id=account.id,
            total_sessions=0,
            total_turns=int(total_turns or 0),
            avg_total=0.0,
            best_total=0,
            active_days=0,
            streak_days=0,
            dimensions=[
                DimensionAverage(key=item.key, name=item.name, average=0.0)
                for item in DIMENSIONS
            ],
            recent=[],
        )

    totals = [row.score_total for row in rows]
    averages: list[DimensionAverage] = []
    for item in DIMENSIONS:
        key = item.key
        column_name = DIMENSION_COLUMNS[key]
        value = sum(int(getattr(row, column_name) or 0) for row in rows) / len(rows)
        averages.append(DimensionAverage(key=key, name=item.name, average=round(value, 1)))

    days = {_as_date(row.created_at) for row in rows}
    recent = [
        RecentRecordOut(
            id=row.id,
            scenario_id=row.scenario_id,
            scenario_name=row.scenario_name,
            score_total=row.score_total,
            created_at=row.created_at,
        )
        for row in rows[:10]
    ]

    return StatsMeOut(
        account_id=account.id,
        total_sessions=len(rows),
        total_turns=int(total_turns or 0),
        avg_total=round(sum(totals) / len(totals), 1),
        best_total=max(totals),
        active_days=len(days),
        streak_days=_streak(days),
        dimensions=averages,
        recent=recent,
    )


def _level(count: int) -> int:
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count <= 3:
        return 2
    if count <= 6:
        return 3
    return 4


async def heatmap(session: AsyncSession, account: Account, *, days: int = 90) -> HeatmapOut:
    days = max(7, min(days, 365))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)

    rows = (
        await session.execute(
            select(TrainingRecord.created_at).where(
                TrainingRecord.owner_id == account.id,
                TrainingRecord.created_at >= datetime.combine(start, datetime.min.time()),
            )
        )
    ).scalars().all()

    counts: dict[date, int] = {}
    for created_at in rows:
        day = _as_date(created_at)
        counts[day] = counts.get(day, 0) + 1

    items: list[HeatmapDayOut] = []
    cursor = start
    while cursor <= today:
        count = counts.get(cursor, 0)
        items.append(
            HeatmapDayOut(
                date=cursor.isoformat(),
                count=count,
                level=_level(count),
            )
        )
        cursor += timedelta(days=1)

    total = sum(item.count for item in items)
    max_count = max((item.count for item in items), default=0)
    return HeatmapOut(days=items, max_count=max_count, total=total)

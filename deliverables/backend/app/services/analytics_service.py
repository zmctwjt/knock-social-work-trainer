"""教师端与管理端的统计分析。

单独成文件的原因：`role_service` 已经承担账号与内容的增删改，再塞统计会让
那个文件两三百行地膨胀。这里只做"读"——聚合训练记录、算维度均值、出趋势。

口径统一说明（避免前端与管理端各算一套）：
- 平均分只用 `training_records.score_total`，一次训练一条记录；
- 维度均值只统计完成过评分的记录，未评分的记录不参与；
- 趋势按自然日聚合，缺失日期补 0，保证折线不断档。
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Account, TrainingRecord, TrainingSession
from app.domain.schemas import (
    AdminTrendOut,
    ClassTrendOut,
    DimensionAvgOut,
    LearnerDetailOut,
    ScenarioUsageOut,
    TrendPointOut,
)

#: 维度键 → 展示名，与前端六维面板保持同一顺序
DIMENSIONS: list[tuple[str, str]] = [
    ("empathy", "同感与倾听"),
    ("question", "提问与对焦"),
    ("advice", "信息与建议"),
    ("ethics", "伦理原则"),
    ("process", "过程完整性"),
    ("risk", "风险识别与转介"),
]

_DIM_COLUMN = {
    "empathy": TrainingRecord.score_empathy,
    "question": TrainingRecord.score_question,
    "advice": TrainingRecord.score_advice,
    "ethics": TrainingRecord.score_ethics,
    "process": TrainingRecord.score_process,
    "risk": TrainingRecord.score_risk,
}


def _day(ts: datetime) -> str:
    return ts.astimezone(UTC).date().isoformat() if ts.tzinfo else ts.date().isoformat()


async def _dimension_averages(
    session: AsyncSession, owner_ids: list[uuid.UUID]
) -> list[DimensionAvgOut]:
    if not owner_ids:
        return []
    row = (
        await session.execute(
            select(
                func.count(TrainingRecord.id),
                *[func.avg(_DIM_COLUMN[key]) for key, _ in DIMENSIONS],
            ).where(TrainingRecord.owner_id.in_(owner_ids))
        )
    ).one()
    total = int(row[0] or 0)
    out: list[DimensionAvgOut] = []
    for index, (key, name) in enumerate(DIMENSIONS, start=1):
        value = row[index]
        out.append(
            DimensionAvgOut(
                key=key,
                name=name,
                avg=round(float(value), 1) if value is not None else 0.0,
                count=total,
            )
        )
    return out


async def _scenario_usage(
    session: AsyncSession, owner_ids: list[uuid.UUID], limit: int = 8
) -> list[ScenarioUsageOut]:
    if not owner_ids:
        return []
    rows = (
        await session.execute(
            select(
                TrainingRecord.scenario_id,
                TrainingRecord.scenario_name,
                func.count(TrainingRecord.id),
                func.avg(TrainingRecord.score_total),
            )
            .where(TrainingRecord.owner_id.in_(owner_ids))
            .group_by(TrainingRecord.scenario_id, TrainingRecord.scenario_name)
            .order_by(func.count(TrainingRecord.id).desc())
            .limit(limit)
        )
    ).all()
    return [
        ScenarioUsageOut(
            scenario_id=row[0],
            scenario_name=row[1] or row[0],
            sessions=int(row[2] or 0),
            avg_total=round(float(row[3]), 1) if row[3] is not None else 0.0,
        )
        for row in rows
    ]


async def _trend(
    session: AsyncSession,
    owner_ids: list[uuid.UUID],
    *,
    days: int = 14,
) -> list[TrendPointOut]:
    """按日聚合，缺失日期补 0（否则折线会在没练的日子里断掉）。"""
    if not owner_ids:
        return []
    since = datetime.now(UTC) - timedelta(days=days - 1)
    rows = (
        await session.execute(
            select(
                TrainingRecord.created_at,
                TrainingRecord.score_total,
            )
            .where(
                TrainingRecord.owner_id.in_(owner_ids),
                TrainingRecord.created_at >= since,
            )
            .order_by(TrainingRecord.created_at)
        )
    ).all()
    bucket: dict[str, list[int]] = defaultdict(list)
    for created_at, score in rows:
        if created_at is None:
            continue
        bucket[_day(created_at)].append(int(score or 0))

    today = datetime.now(UTC).date()
    points: list[TrendPointOut] = []
    for offset in range(days - 1, -1, -1):
        day: date = today - timedelta(days=offset)
        scores = bucket.get(day.isoformat(), [])
        points.append(
            TrendPointOut(
                date=day.isoformat(),
                sessions=len(scores),
                avg_total=round(sum(scores) / len(scores), 1) if scores else 0.0,
            )
        )
    return points


# ═══════════════════════════════════════════════════════════
# 教师端
# ═══════════════════════════════════════════════════════════


async def learner_detail(
    session: AsyncSession, owner_ids: list[uuid.UUID], account: Account
) -> LearnerDetailOut:
    """单个学员的完整画像：总量、维度、趋势、案例分布。"""
    records = (
        await session.execute(
            select(TrainingRecord)
            .where(TrainingRecord.owner_id == account.id)
            .order_by(TrainingRecord.created_at.desc())
        )
    ).scalars().all()
    totals = [int(r.score_total or 0) for r in records]
    dimensions = await _dimension_averages(session, [account.id])

    finished_sessions = (
        await session.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.owner_id == account.id,
                TrainingSession.status == "finished",
            )
        )
    ).scalar_one()

    total_turns = (
        await session.execute(
            select(func.coalesce(func.sum(TrainingSession.turn_count), 0)).where(
                TrainingSession.owner_id == account.id
            )
        )
    ).scalar_one()

    weakest = ""
    weakest_val = 1000.0
    for item in dimensions:
        if item.avg and item.avg < weakest_val:
            weakest_val = item.avg
            weakest = item.key

    return LearnerDetailOut(
        account_id=account.id,
        username=account.username,
        nickname=account.nickname,
        is_active=account.is_active,
        last_login_at=account.last_login_at,
        sessions=len(records),
        finished=int(finished_sessions or 0),
        avg_total=round(sum(totals) / len(totals), 1) if totals else 0.0,
        best_total=max(totals) if totals else 0,
        total_turns=int(total_turns or 0),
        total_minutes=round(sum(int(r.duration_sec or 0) for r in records) / 60),
        dimensions=dimensions,
        weakest=weakest,
        trend=await _trend(session, [account.id], days=14),
        scenarios=await _scenario_usage(session, [account.id]),
    )


async def class_trend(
    session: AsyncSession, owner_ids: list[uuid.UUID], *, days: int = 14
) -> ClassTrendOut:
    return ClassTrendOut(
        points=await _trend(session, owner_ids, days=days),
        dimensions=await _dimension_averages(session, owner_ids),
        scenarios=await _scenario_usage(session, owner_ids),
    )


# ═══════════════════════════════════════════════════════════
# 管理端
# ═══════════════════════════════════════════════════════════


async def admin_trend(session: AsyncSession, *, days: int = 30) -> AdminTrendOut:
    """全平台趋势：训练量、维度均值、案例热度、角色分布。"""
    all_owners = list(
        (await session.execute(select(Account.id))).scalars().all()
    )
    role_rows = (
        await session.execute(
            select(Account.role, func.count(Account.id)).group_by(Account.role)
        )
    ).all()
    return AdminTrendOut(
        days=days,
        points=await _trend(session, all_owners, days=days),
        role_distribution={str(row[0]): int(row[1]) for row in role_rows},
        scenario_usage=await _scenario_usage(session, all_owners, limit=10),
        dimensions=await _dimension_averages(session, all_owners),
    )
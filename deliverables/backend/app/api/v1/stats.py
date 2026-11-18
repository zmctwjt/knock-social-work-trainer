"""个人统计：看板聚合与训练热力图。

口径说明：只统计 `training_records`（已结案快照）。未结案的会话不计入
平均分与连续天数——避免"练到一半不结案"把数据刷高。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, SessionDep
from app.core.response import ok
from app.domain.schemas import Envelope, HeatmapOut, StatsMeOut
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["统计"])


@router.get("/me", response_model=Envelope[StatsMeOut], summary="我的训练看板")
async def my_stats(account: CurrentUser, session: SessionDep):
    return ok(await stats_service.me(session, account))


@router.get("/heatmap", response_model=Envelope[HeatmapOut], summary="训练热力图")
async def heatmap(
    account: CurrentUser,
    session: SessionDep,
    days: int = Query(default=90, ge=7, le=365),
):
    return ok(await stats_service.heatmap(session, account, days=days))

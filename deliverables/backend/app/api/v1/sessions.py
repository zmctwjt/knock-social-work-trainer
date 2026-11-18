"""训练会话：创建、列表、详情、发言、分段评分、结案、复盘。

所有读写都以「先查再比 owner_id」的方式做授权——原 Supabase RLS 在新库中
由应用层显式过滤替代（见第 6 章迁移说明），越权返回 40301 而非 40401，
与旧前端的错误提示保持一致。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import GatewayDep
from app.core.deps import AdminUser, CurrentUser, HumanUser, SessionDep
from app.core.response import ok
from app.domain.enums import SessionStatus
from app.domain.models import TrainingSession
from app.domain.schemas import (
    DebriefOut,
    Envelope,
    FinishOut,
    ScoringOut,
    SessionCreateRequest,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    StageScoreOut,
    TurnCreateRequest,
    TurnPairOut,
)
from app.services import session_service

router = APIRouter(prefix="/sessions", tags=["训练会话"])


@router.post("", response_model=Envelope[SessionOut], summary="创建训练会话")
async def create_session(
    payload: SessionCreateRequest, account: HumanUser, session: SessionDep
):
    result = await session_service.create_session(
        session,
        account,
        scenario_id=payload.scenario_id,
        difficulty=payload.difficulty,
        blindfold=payload.blindfold,
        max_turns=payload.max_turns,
        client_session_id=payload.client_session_id,
    )
    return ok(result, message="会话已创建")


@router.get("", response_model=Envelope[SessionListOut], summary="我的会话列表")
async def list_sessions(
    account: CurrentUser,
    session: SessionDep,
    status: SessionStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items = await session_service.list_sessions(
        session, account, status=status, limit=limit, offset=offset
    )
    total = (
        await session.execute(
            select(func.count(TrainingSession.id)).where(
                TrainingSession.owner_id == account.id
            )
        )
    ).scalar_one()
    return ok(SessionListOut(items=items, total=int(total or 0)))


@router.get(
    "/{session_id}", response_model=Envelope[SessionDetailOut], summary="会话详情"
)
async def get_session(session_id: uuid.UUID, account: CurrentUser, session: SessionDep):
    detail = await session_service.get_session_detail(session, account, session_id)
    return ok(detail)


@router.post(
    "/{session_id}/turns",
    response_model=Envelope[TurnPairOut],
    summary="提交一句学生发言并取得角色回应",
)
async def submit_turn(
    session_id: uuid.UUID,
    payload: TurnCreateRequest,
    account: HumanUser,
    session: SessionDep,
    gateway: GatewayDep,
):
    pair = await session_service.submit_turn(
        session,
        account,
        session_id,
        text=payload.text,
        client_turn_id=payload.client_turn_id,
        stage=payload.stage,
        gateway=gateway,
    )
    return ok(pair)


@router.post(
    "/{session_id}/stages/{stage_index}/score",
    response_model=Envelope[ScoringOut],
    summary="分段评分",
)
async def score_stage(
    session_id: uuid.UUID,
    stage_index: int,
    account: HumanUser,
    session: SessionDep,
    gateway: GatewayDep,
):
    result = await session_service.score_stage(
        session, account, session_id, stage_index=stage_index, gateway=gateway
    )
    return ok(result)


@router.post(
    "/{session_id}/finish", response_model=Envelope[FinishOut], summary="结案并写入训练记录"
)
async def finish_session(
    session_id: uuid.UUID, account: HumanUser, session: SessionDep
):
    result = await session_service.finish_session(session, account, session_id)
    return ok(result, message="已结案")


@router.post(
    "/{session_id}/debrief", response_model=Envelope[DebriefOut], summary="生成三段式复盘"
)
async def debrief_session(
    session_id: uuid.UUID,
    account: HumanUser,
    session: SessionDep,
    gateway: GatewayDep,
):
    result = await session_service.debrief_session(
        session, account, session_id, gateway=gateway
    )
    return ok(result)


@router.delete("/{session_id}", response_model=Envelope[dict], summary="删除会话（管理员）")
async def delete_session(session_id: uuid.UUID, account: AdminUser, session: SessionDep):
    await session_service.delete_session(session, account, session_id)
    return ok({"deleted": True}, message="已删除")


__all__ = ["router", "StageScoreOut"]

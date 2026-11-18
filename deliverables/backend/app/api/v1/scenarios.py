"""案例与知识卡：只读内容接口。

内容在启动时由 `content_service.seed_content()` 幂等灌入数据库，
接口层不做任何写操作——12 个角色、19 张技巧卡是教学资产，不允许运行时被改。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import SessionDep
from app.core.response import ok
from app.domain.models import Scenario
from app.domain.schemas import (
    Envelope,
    KnowledgeCardListOut,
    KnowledgeCardOut,
    ScenarioListOut,
    ScenarioOut,
    difficulty_label_of,
)
from app.services import content_service

router = APIRouter(tags=["案例与知识卡"])


def _scenario_out(row: Scenario) -> ScenarioOut:
    return ScenarioOut(
        id=row.id,
        name=row.name,
        age=row.age,
        gender=row.gender,
        archetype=row.archetype,
        difficulty=row.difficulty,
        difficulty_label=difficulty_label_of(row.difficulty),
        resistance=row.resistance,
        sensitive_tag=row.sensitive_tag,
        brief=row.brief,
        initial_emotion=row.initial_emotion,
        active=row.active,
    )


@router.get("/scenarios", response_model=Envelope[ScenarioListOut], summary="案例列表")
async def list_scenarios(
    session: SessionDep,
    include_inactive: bool = Query(default=False),
):
    rows = await content_service.list_scenarios(session, include_inactive=include_inactive)
    items = [_scenario_out(row) for row in rows]
    return ok(ScenarioListOut(items=items, total=len(items)))


@router.get("/scenarios/{scenario_id}", response_model=Envelope[ScenarioOut], summary="案例详情")
async def get_scenario(scenario_id: str, session: SessionDep):
    row = await content_service.get_scenario(session, scenario_id)
    return ok(_scenario_out(row))


@router.get(
    "/knowledge/cards",
    response_model=Envelope[KnowledgeCardListOut],
    summary="技巧卡列表",
)
async def list_cards(
    session: SessionDep,
    category: str | None = Query(default=None, max_length=32),
    keyword: str | None = Query(default=None, max_length=64, description="按标题/摘要/正文包含匹配"),
):
    rows = await content_service.list_cards(session, category=category, keyword=keyword)
    items = [KnowledgeCardOut.model_validate(row) for row in rows]
    return ok(KnowledgeCardListOut(items=items, total=len(items)))

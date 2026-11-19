"""案例与知识卡：只读内容接口。

内容在启动时由 `content_service.seed_content()` 幂等灌入数据库。
本文件只提供**只读**接口；写操作在管理端（`/admin/*`）与教师端
（`/teacher/scenarios`）。每个案例带 `custom` / `editable` 标记，
供界面决定是否显示编辑入口（内置案例仅管理员可改）。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import OptionalUser, SessionDep
from app.core.response import ok
from app.domain.enums import Role
from app.domain.models import Account, Scenario
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


def can_edit_scenario(row: Scenario, viewer: Account | None) -> bool:
    """判定某账号能否编辑该案例。

    规则（与任务书的角色分工一致）：
    - 内置案例（created_by 为空）：只有管理员能改，教师不能动课程自带内容；
    - 自建案例：创建者本人与管理员能改，别的教师看不到编辑入口。
    """
    if viewer is None:
        return False
    if viewer.role == Role.ADMIN.value:
        return True
    if viewer.role == Role.TEACHER.value:
        return row.created_by is not None and row.created_by == viewer.id
    return False


def _scenario_out(
    row: Scenario, viewer: Account | None = None, owner_name: str | None = None
) -> ScenarioOut:
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
        custom=row.created_by is not None,
        created_by=row.created_by,
        owner_name=owner_name,
        editable=can_edit_scenario(row, viewer),
    )


@router.get("/scenarios", response_model=Envelope[ScenarioListOut], summary="案例列表")
async def list_scenarios(
    session: SessionDep,
    include_inactive: bool = Query(default=False),
    viewer: OptionalUser = None,
):
    rows = await content_service.list_scenarios(session, include_inactive=include_inactive)
    owners = await content_service.scenario_owner_names(session, rows)
    items = [_scenario_out(row, viewer, owners.get(row.created_by)) for row in rows]
    return ok(ScenarioListOut(items=items, total=len(items)))


@router.get("/scenarios/{scenario_id}", response_model=Envelope[ScenarioOut], summary="案例详情")
async def get_scenario(
    scenario_id: str, session: SessionDep, viewer: OptionalUser = None
):
    row = await content_service.get_scenario(session, scenario_id)
    return ok(_scenario_out(row, viewer))


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

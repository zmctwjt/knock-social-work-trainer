"""/api/v1 教师端与管理端路由。

权限口径（表 5-5）：
- `/teacher/*`：仅教师与管理员，教师只能看自己名下学员；
- `/admin/*`：仅管理员，覆盖账号、内容、运行状态三类操作。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, SessionDep, SettingsDep, require_roles
from app.core.errors import AppError
from app.core.response import ok
from app.domain.enums import Role
from app.domain.schemas import (
    AccountActiveRequest,
    AccountCreateRequest,
    BindLearnerRequest,
    CardUpsertRequest,
    ScenarioUpsertRequest,
)
from app.domain.schemas import (
    BulkActiveRequest,
    BulkResultOut,
    RuleWordIn,
    ScriptLineIn,
    ScriptLinePatch,
)
from app.services import (
    analytics_service,
    role_service,
    rule_word_service,
    script_line_service,
)

TeacherUser = Depends(require_roles(Role.TEACHER, Role.ADMIN))
AdminUser = Depends(require_roles(Role.ADMIN))

teacher_router = APIRouter(prefix="/teacher", tags=["教师端"], dependencies=[TeacherUser])
admin_router = APIRouter(prefix="/admin", tags=["管理端"], dependencies=[AdminUser])


# ── 教师端 ──────────────────────────────────────────────────
@teacher_router.get("/learners", summary="名下学员列表")
async def teacher_learners(account: CurrentUser, session: SessionDep):
    return ok(await role_service.list_learners(session, account))


@teacher_router.get("/stats", summary="班级看板")
async def teacher_stats(account: CurrentUser, session: SessionDep):
    return ok(await role_service.class_stats(session, account))


@teacher_router.get("/learners/{owner_id}/records", summary="查看学员训练记录（分页）")
async def teacher_learner_records(
    owner_id: uuid.UUID,
    account: CurrentUser,
    session: SessionDep,
    page: int = 1,
    page_size: int = 20,
):
    return ok(
        await role_service.learner_records(
            session, account, owner_id, page=page, page_size=page_size
        )
    )


@teacher_router.post("/learners", summary="绑定学员到名下")
async def teacher_bind_learner(
    payload: BindLearnerRequest, account: CurrentUser, session: SessionDep
):
    return ok((await role_service.bind_learner(session, account, payload.username)).model_dump())


# ── 管理端：账号 ────────────────────────────────────────────
@admin_router.get("/overview", summary="运行概览")
async def admin_overview(account: CurrentUser, session: SessionDep, settings: SettingsDep):
    return ok((await role_service.admin_overview(session, settings)).model_dump())


@admin_router.get("/accounts", summary="账号列表")
async def admin_accounts(
    account: CurrentUser,
    session: SessionDep,
    role: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    return ok(
        (
            await role_service.admin_list_accounts(
                session, role=role, keyword=keyword, page=page, page_size=page_size
            )
        ).model_dump()
    )


@admin_router.post("/accounts", summary="新建账号（教务导入）")
async def admin_create_account(
    payload: AccountCreateRequest, account: CurrentUser, session: SessionDep, settings: SettingsDep
):
    out = await role_service.admin_create_account(
        session,
        settings,
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        role=payload.role,
    )
    return ok(out.model_dump(), message="账号已创建")


@admin_router.patch("/accounts/{account_id}/active", summary="启用 / 停用账号")
async def admin_set_active(
    account_id: uuid.UUID,
    payload: AccountActiveRequest,
    account: CurrentUser,
    session: SessionDep,
):
    out = await role_service.admin_set_active(
        session, account_id=account_id, active=payload.active
    )
    return ok(out.model_dump(), message="已更新")


# ── 管理端：内容维护 ────────────────────────────────────────
@admin_router.post("/scenarios", summary="新建或编辑案例")
async def admin_upsert_scenario(
    payload: ScenarioUpsertRequest, account: CurrentUser, session: SessionDep
):
    out = await role_service.upsert_scenario(session, payload)
    return ok(out.model_dump(), message="案例已保存")


@admin_router.delete("/scenarios/{scenario_id}", summary="下架案例")
async def admin_archive_scenario(
    scenario_id: str, account: CurrentUser, session: SessionDep
):
    return ok((await role_service.archive_scenario(session, scenario_id)).model_dump())


@admin_router.post("/cards", summary="新建或编辑技巧卡")
async def admin_upsert_card(
    payload: CardUpsertRequest, account: CurrentUser, session: SessionDep
):
    out = await role_service.upsert_card(session, payload)
    return ok(out.model_dump(), message="技巧卡已保存")


@admin_router.delete("/cards/{card_id}", summary="删除技巧卡")
async def admin_delete_card(card_id: str, account: CurrentUser, session: SessionDep):
    return ok((await role_service.delete_card(session, card_id)).model_dump())


# ── 管理端：系统 ────────────────────────────────────────────
@admin_router.get("/ai-logs", summary="AI 调用审计日志（含成功率与平均延迟）")
async def admin_ai_logs(
    account: CurrentUser,
    session: SessionDep,
    limit: int = 50,
    purpose: str | None = None,
    status: str | None = None,
):
    return ok(
        await role_service.admin_ai_logs(
            session, limit=limit, purpose=purpose, status=status
        )
    )


# ── 管理端：判定词表维护 ────────────────────────────────────
@admin_router.get("/rule-words", summary="判定词表（分组与自定义词）")
async def admin_rule_words(account: CurrentUser, session: SessionDep):
    return ok(await rule_word_service.list_groups(session))


@admin_router.post("/rule-words", summary="追加词条")
async def admin_add_rule_word(
    payload: RuleWordIn, account: CurrentUser, session: SessionDep
):
    out = await rule_word_service.add_word(
        session, group=payload.group, word=payload.word, note=payload.note
    )
    return ok(out, message="词条已追加")


@admin_router.delete("/rule-words/entry/{word_id}", summary="删除自定义词条")
async def admin_remove_rule_word(
    word_id: uuid.UUID, account: CurrentUser, session: SessionDep
):
    return ok(await rule_word_service.remove_custom_word(session, word_id))


@admin_router.delete("/rule-words/{group}/{word}", summary="禁用词条")
async def admin_disable_rule_word(
    group: str, word: str, account: CurrentUser, session: SessionDep
):
    out = await rule_word_service.disable_word(session, group=group, word=word)
    return ok(out, message="词条已禁用")


# ── 管理端：台词节点维护 ────────────────────────────────────
@admin_router.get("/script-lines", summary="台词节点列表")
async def admin_script_lines(
    account: CurrentUser, session: SessionDep, scenario_id: str | None = None
):
    return ok(await script_line_service.list_lines(session, scenario_id=scenario_id))


@admin_router.post("/script-lines", summary="新增台词")
async def admin_create_script_line(
    payload: ScriptLineIn, account: CurrentUser, session: SessionDep
):
    out = await script_line_service.create_line(
        session,
        text=payload.text,
        emotion_bucket=payload.emotion_bucket,
        scenario_id=payload.scenario_id,
        order_index=payload.order_index,
    )
    return ok(out, message="台词已新增")


@admin_router.patch("/script-lines/{line_id}", summary="编辑台词")
async def admin_update_script_line(
    line_id: uuid.UUID, payload: ScriptLinePatch, account: CurrentUser, session: SessionDep
):
    out = await script_line_service.update_line(
        session,
        line_id,
        text=payload.text,
        emotion_bucket=payload.emotion_bucket,
        order_index=payload.order_index,
        active=payload.active,
    )
    return ok(out, message="台词已更新")


@admin_router.delete("/script-lines/{line_id}", summary="删除台词")
async def admin_delete_script_line(
    line_id: uuid.UUID, account: CurrentUser, session: SessionDep
):
    return ok(await script_line_service.delete_line(session, line_id))


# ── 教师端：扩展分析 ────────────────────────────────────────
@teacher_router.get("/learners/{owner_id}/detail", summary="学员完整画像")
async def teacher_learner_detail(
    owner_id: uuid.UUID, account: CurrentUser, session: SessionDep
):
    from app.domain.models import Account

    target = await session.get(Account, owner_id)
    if target is None:
        raise AppError.not_found("学员不存在")
    # 归属校验：非本人名下学员一律 403，避免通过 ID 探测他人数据
    allowed = await role_service.learner_ids(session, account)
    if account.role != Role.ADMIN.value and owner_id not in allowed:
        raise AppError.forbidden("只能查看名下学员")
    return ok((await analytics_service.learner_detail(session, allowed, target)).model_dump())


@teacher_router.get("/trend", summary="班级趋势与维度分布")
async def teacher_trend(account: CurrentUser, session: SessionDep, days: int = 14):
    ids = await role_service.learner_ids(session, account)
    out = await analytics_service.class_trend(session, ids, days=max(1, min(days, 90)))
    return ok(out.model_dump())


# ── 管理端：平台趋势 ────────────────────────────────────────
@admin_router.get("/trend", summary="平台趋势与分布")
async def admin_trend(account: CurrentUser, session: SessionDep, days: int = 30):
    out = await analytics_service.admin_trend(session, days=max(1, min(days, 180)))
    return ok(out.model_dump())


@admin_router.post("/accounts/bulk-active", summary="批量启用 / 停用账号")
async def admin_bulk_active(
    payload: BulkActiveRequest, account: CurrentUser, session: SessionDep
):
    updated = failed = 0
    messages: list[str] = []
    for account_id in payload.account_ids:
        try:
            await role_service.admin_set_active(
                session, account_id=account_id, active=payload.active
            )
            updated += 1
        except AppError as exc:
            failed += 1
            messages.append(f"{account_id}: {exc.message}")
    return ok(
        BulkResultOut(updated=updated, failed=failed, messages=messages).model_dump(),
        message=f"已更新 {updated} 个账号",
    )

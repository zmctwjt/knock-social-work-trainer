"""多角色能力：教师（班级看板／查看学员记录）与管理员（账号、内容、运行状态）。

设计依据见 `docs/05_Python后端详细设计.md` 表 5-5 角色权限矩阵与任务书
"管理端：账号管理／数据统计／内容维护／系统管理"四项。

授权口径：
- 教师只能看到**自己名下学员**的记录；跨班返回空集而非报错（表 5-5 F12 验收项）；
- 管理员可跨班查看、可停用账号、可维护内容；
- 所有写操作走 `require_roles` 守卫，越权统一 40301。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.enums import Role
from app.domain.models import (
    Account,
    AiAuditLog,
    KnowledgeCard,
    Scenario,
    TrainingRecord,
    TrainingSession,
)
from app.domain.schemas import (
    AdminOverviewOut,
    AccountOut,
    AccountAdminOut,
    AccountListOut,
    CardUpsertRequest,
    KnowledgeCardOut,
    ScenarioOut,
    ClassStatsOut,
    LearnerRecordOut,
    LearnerListOut,
    MessageOut,
    ScenarioUpsertRequest,
)
from app.services.account_service import _account_out


def _scenario_out(row: Scenario) -> ScenarioOut:
    """复用列表接口的序列化口径（含 difficulty_label），避免两处字段不一致。"""
    from app.api.v1.scenarios import _scenario_out as _impl

    return _impl(row)


# ═══════════════════════════════════════════════════════════
# 一、教师端：班级看板与学员记录
# ═══════════════════════════════════════════════════════════


async def _my_learners(session: AsyncSession, teacher: Account) -> list[Account]:
    """教师名下学员：按 `teacher_id` 归属过滤（应用层强制隔离，不用 RLS）。"""
    rows = await session.execute(
        select(Account)
        .where(Account.teacher_id == teacher.id, Account.is_guest.is_(False))
        .order_by(Account.created_at)
    )
    return list(rows.scalars())


async def list_learners(session: AsyncSession, teacher: Account) -> LearnerListOut:
    learners = await _my_learners(session, teacher)
    if not learners:
        return LearnerListOut(items=[], total=0)
    ids = [x.id for x in learners]

    stats = dict(
        (
            await session.execute(
                select(TrainingRecord.owner_id, func.count(TrainingRecord.id))
                .where(TrainingRecord.owner_id.in_(ids))
                .group_by(TrainingRecord.owner_id)
            )
        ).all()
    )
    avg = dict(
        (
            await session.execute(
                select(TrainingRecord.owner_id, func.avg(TrainingRecord.score_total))
                .where(TrainingRecord.owner_id.in_(ids))
                .group_by(TrainingRecord.owner_id)
            )
        ).all()
    )
    items = [
        LearnerRecordOut(
            account_id=x.id,
            username=x.username,
            nickname=x.nickname,
            sessions=int(stats.get(x.id, 0)),
            avg_total=round(float(avg[x.id]), 1) if avg.get(x.id) is not None else 0.0,
            is_active=x.is_active,
            last_login_at=x.last_login_at,
        )
        for x in learners
    ]
    return LearnerListOut(items=items, total=len(items))


async def class_stats(session: AsyncSession, teacher: Account) -> ClassStatsOut:
    """班级聚合：学员数、训练总量、平均分与维度均值、最薄弱维度。"""
    learners = await _my_learners(session, teacher)
    if not learners:
        return ClassStatsOut(
            learners=0, sessions=0, avg_total=0.0, dimensions={}, weakest="", weakest_score=0.0
        )
    ids = [x.id for x in learners]
    row = (
        await session.execute(
            select(
                func.count(TrainingRecord.id),
                func.avg(TrainingRecord.score_total),
                func.avg(TrainingRecord.score_empathy),
                func.avg(TrainingRecord.score_question),
                func.avg(TrainingRecord.score_advice),
                func.avg(TrainingRecord.score_ethics),
                func.avg(TrainingRecord.score_process),
                func.avg(TrainingRecord.score_risk),
            ).where(TrainingRecord.owner_id.in_(ids))
        )
    ).one()
    names = ["empathy", "question", "advice", "ethics", "process", "risk"]
    dimensions = {
        name: round(float(val), 1) for name, val in zip(names, row[2:], strict=True) if val is not None
    }
    weakest = min(dimensions, key=lambda k: dimensions[k]) if dimensions else ""
    return ClassStatsOut(
        learners=len(learners),
        sessions=int(row[0] or 0),
        avg_total=round(float(row[1]), 1) if row[1] is not None else 0.0,
        dimensions=dimensions,
        weakest=weakest,
        weakest_score=dimensions.get(weakest, 0.0),
    )


async def learner_records(
    session: AsyncSession,
    teacher: Account,
    owner_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    """查看指定学员记录（分页）。

    归属校验走 `learner_ids`，与详情、趋势接口同一口径：
    教师只能看名下，管理员可看全部；非名下返回空集而非报错，避免泄露存在性。
    """
    allowed = await learner_ids(session, teacher)
    target = await session.get(Account, owner_id)
    if target is None or owner_id not in allowed:
        return {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 0}

    size = max(1, min(page_size, 100))
    current = max(1, page)
    total = int(
        (
            await session.execute(
                select(func.count(TrainingRecord.id)).where(
                    TrainingRecord.owner_id == owner_id
                )
            )
        ).scalar_one()
        or 0
    )
    rows = await session.execute(
        select(TrainingRecord)
        .where(TrainingRecord.owner_id == owner_id)
        .order_by(TrainingRecord.created_at.desc())
        .offset((current - 1) * size)
        .limit(size)
    )
    items = [
        LearnerRecordOut(
            account_id=owner_id,
            username=target.username,
            nickname=target.nickname,
            sessions=1,
            avg_total=float(rec.score_total),
            is_active=target.is_active,
            last_login_at=target.last_login_at,
            scenario_name=rec.scenario_name,
            score_total=rec.score_total,
            created_at=rec.created_at,
        ).model_dump()
        for rec in rows.scalars()
    ]
    return {
        "items": items,
        "total": total,
        "page": current,
        "page_size": size,
        "pages": (total + size - 1) // size if total else 0,
    }


async def bind_learner(
    session: AsyncSession, teacher: Account, learner_username: str
) -> MessageOut:
    """把学员挂到当前教师名下（简易版班级归属，二期换班级实体）。"""
    learner = (
        await session.execute(
            select(Account).where(Account.username == learner_username.strip().lower())
        )
    ).scalar_one_or_none()
    if learner is None:
        raise AppError.not_found("学员账号不存在，请先在管理员端创建")
    if learner.role != Role.STUDENT.value:
        raise AppError.bad_request("只能绑定学生账号")
    if learner.teacher_id is not None and learner.teacher_id != teacher.id:
        raise AppError.conflict("该学员已归属其他教师")
    learner.teacher_id = teacher.id
    await session.commit()
    return MessageOut(message=f"已将 {learner.nickname} 加入名下学员")


# ═══════════════════════════════════════════════════════════
# 二、管理员端：账号管理
# ═══════════════════════════════════════════════════════════


def _admin_out(account: Account) -> AccountAdminOut:
    base = _account_out(account)
    return AccountAdminOut(
        **base.model_dump(),
        is_active=account.is_active,
        teacher_id=account.teacher_id,
        last_login_at=account.last_login_at,
    )


async def admin_list_accounts(
    session: AsyncSession,
    *,
    role: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> AccountListOut:
    """账号分页查询。

    用 offset 分页而非游标：账号按 created_at 排序且变动不频繁，
    教务场景需要"跳到第 N 页"，游标分页反而不好用。
    总数单独 count，不能拿本页长度充数（那会让前端算出错误的页数）。
    """
    size = max(1, min(page_size, 200))
    current = max(1, page)

    filters = []
    if role:
        filters.append(Account.role == role)
    if keyword:
        like = f"%{keyword.strip()}%"
        filters.append((Account.username.like(like)) | (Account.nickname.like(like)))

    count_stmt = select(func.count(Account.id))
    stmt = select(Account).order_by(Account.created_at.desc())
    for f in filters:
        count_stmt = count_stmt.where(f)
        stmt = stmt.where(f)

    total = int((await session.execute(count_stmt)).scalar_one() or 0)
    rows = await session.execute(stmt.offset((current - 1) * size).limit(size))
    items = [_admin_out(x) for x in rows.scalars()]
    return AccountListOut(
        items=items,
        total=total,
        page=current,
        page_size=size,
        pages=(total + size - 1) // size if total else 0,
    )


async def admin_create_account(
    session: AsyncSession,
    settings: Settings,
    *,
    username: str,
    password: str,
    nickname: str | None,
    role: str,
) -> AccountAdminOut:
    """管理端建号（教务导入场景，不开放自助注册）。"""
    from app.services.account_service import create_account

    if role not in {r.value for r in Role if r is not Role.GUEST}:
        raise AppError.bad_request("角色只能是 student / teacher / admin")
    existing = (
        await session.execute(select(Account).where(Account.username == username))
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError.conflict("该用户名已存在")
    account = await create_account(
        session, settings, username=username, password=password,
        nickname=nickname, role=Role(role),
    )
    return _admin_out(account)


async def admin_set_active(
    session: AsyncSession, *, account_id: uuid.UUID, active: bool
) -> AccountAdminOut:
    account = await session.get(Account, account_id)
    if account is None:
        raise AppError.not_found("账号不存在")
    if account.is_guest:
        raise AppError.bad_request("游客账号无需停用")
    account.is_active = active
    await session.commit()
    await session.refresh(account)
    return _admin_out(account)


# ═══════════════════════════════════════════════════════════
# 三、管理员端：内容维护
# ═══════════════════════════════════════════════════════════


def _scenario_payload(body: ScenarioUpsertRequest, current: Scenario | None) -> dict:
    # exclude_unset：编辑时只改显式传入的字段；再剔除 None，避免覆盖成 NULL
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if current is None:
        for field in ("name", "age", "gender", "archetype", "brief", "system_prompt"):
            if not data.get(field):
                raise AppError.bad_request(f"新建案例必须提供 {field}")
    return data


async def upsert_scenario(
    session: AsyncSession, body: ScenarioUpsertRequest
) -> ScenarioOut:
    current = await session.get(Scenario, body.id)
    data = _scenario_payload(body, current)
    if current is None:
        data.pop("id", None)
        current = Scenario(id=body.id, **data)
        session.add(current)
    else:
        for key, value in data.items():
            if key != "id":
                setattr(current, key, value)
    await session.commit()
    await session.refresh(current)
    return _scenario_out(current)


async def archive_scenario(session: AsyncSession, scenario_id: str) -> MessageOut:
    """下架而非物理删除：历史训练记录仍需外键指向它。"""
    current = await session.get(Scenario, scenario_id)
    if current is None:
        raise AppError.not_found("案例不存在")
    current.active = False
    await session.commit()
    return MessageOut(message=f"案例 {scenario_id} 已下架")


async def upsert_card(session: AsyncSession, body: CardUpsertRequest) -> KnowledgeCardOut:
    current = await session.get(KnowledgeCard, body.id)
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if current is None:
        if not data.get("title"):
            raise AppError.bad_request("新建技巧卡必须提供 title")
        data.pop("id", None)
        current = KnowledgeCard(id=body.id, **data)
        session.add(current)
    else:
        for key, value in data.items():
            if key != "id":
                setattr(current, key, value)
    await session.commit()
    await session.refresh(current)
    return KnowledgeCardOut.model_validate(current)


async def delete_card(session: AsyncSession, card_id: str) -> MessageOut:
    current = await session.get(KnowledgeCard, card_id)
    if current is None:
        raise AppError.not_found("技巧卡不存在")
    await session.delete(current)
    await session.commit()
    return MessageOut(message=f"技巧卡 {card_id} 已删除")


# ═══════════════════════════════════════════════════════════
# 四、管理员端：系统管理（运行状态 / 配额 / 日志）
# ═══════════════════════════════════════════════════════════


async def admin_overview(session: AsyncSession, settings: Settings) -> AdminOverviewOut:
    """运行概览：账号与训练总量、24 小时 AI 调用、今日配额余量。"""
    accounts = (await session.execute(select(func.count(Account.id)))).scalar_one()
    teachers = (
        await session.execute(
            select(func.count(Account.id)).where(Account.role == Role.TEACHER.value)
        )
    ).scalar_one()
    sessions = (await session.execute(select(func.count(TrainingSession.id)))).scalar_one()
    records = (await session.execute(select(func.count(TrainingRecord.id)))).scalar_one()
    since = datetime.now(UTC) - timedelta(hours=24)
    ai_24h = (
        await session.execute(
            select(func.count(AiAuditLog.id)).where(AiAuditLog.created_at >= since)
        )
    ).scalar_one()
    return AdminOverviewOut(
        accounts=int(accounts),
        teachers=int(teachers),
        sessions=int(sessions),
        records=int(records),
        ai_calls_24h=int(ai_24h),
        ai_configured=settings.ai_configured,
        model_chain=settings.model_chain,
        daily_cap=settings.glm_daily_cap,
        environment=settings.app_env,
    )


async def admin_ai_logs(
    session: AsyncSession,
    *,
    limit: int = 50,
    purpose: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """AI 审计日志 + 汇总指标。

    除了逐条列表，还算成功率与平均延迟——排障时最先看的就是这两个数，
    让管理端不用导出日志再自己算。
    """
    stmt = select(AiAuditLog).order_by(AiAuditLog.created_at.desc())
    if purpose:
        stmt = stmt.where(AiAuditLog.purpose == purpose)
    if status:
        stmt = stmt.where(AiAuditLog.status == status)
    rows = (await session.execute(stmt.limit(max(1, min(limit, 500))))).scalars().all()

    total = (
        await session.execute(select(func.count(AiAuditLog.id)))
    ).scalar_one()
    ok_count = (
        await session.execute(
            select(func.count(AiAuditLog.id)).where(AiAuditLog.status == "ok")
        )
    ).scalar_one()
    avg_latency = (
        await session.execute(select(func.avg(AiAuditLog.latency_ms)))
    ).scalar_one()

    items = [
        {
            "id": str(row.id),
            "purpose": row.purpose,
            "status": row.status,
            "model": row.model,
            "latency_ms": row.latency_ms,
            "degrade_reason": row.degrade_reason,
            "used_ai": row.used_ai,
            "cache_hit": row.cache_hit,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "all_total": int(total or 0),
        "success_rate": round(int(ok_count or 0) / int(total) * 100, 1) if total else 0.0,
        "avg_latency_ms": int(avg_latency) if avg_latency else 0,
    }

async def learner_ids(session: AsyncSession, teacher: Account) -> list[uuid.UUID]:
    """名下学员 ID 列表。管理员返回全部学生/教师 ID，便于"查看全部"。

    抽出来是因为归属校验在多个入口重复出现（详情、趋势、记录），
    集中一处可以保证口径一致——不会出现某个接口忘了过滤的情况。
    """
    if teacher.role == Role.ADMIN.value:
        rows = await session.execute(
            select(Account.id).where(Account.is_guest.is_(False))
        )
        return list(rows.scalars())
    learners = await _my_learners(session, teacher)
    return [x.id for x in learners]

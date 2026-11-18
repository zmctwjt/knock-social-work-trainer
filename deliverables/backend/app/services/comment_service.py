"""教师点评业务逻辑。

权限边界（与训练记录同口径）：
- 教师：可对**名下学员**的记录点评，可查看自己写过的点评；
- 管理员：可对任意记录点评，可查看全部；
- 学生：只能看自己的点评，且看到的是"已发布"的（不区分草稿，本项目无草稿）；
- 客人：不可见。

越权一律 403（不是 404）——因为记录本身对学生可见，
返回 404 会让前端误以为记录被删了。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.enums import Role
from app.domain.models import Account, TeacherComment, TrainingRecord
from app.domain.schemas import CommentListOut, CommentOut

LEVEL_LABEL = {
    "good": "表现良好",
    "watch": "需关注",
    "urgent": "需干预",
}


def _to_out(
    row: TeacherComment,
    teacher: Account | None,
    learner: Account | None,
    record: TrainingRecord | None,
) -> CommentOut:
    return CommentOut(
        id=str(row.id),
        record_id=str(row.record_id),
        teacher_id=str(row.teacher_id),
        teacher_name=teacher.nickname if teacher else "",
        learner_id=str(row.learner_id),
        learner_name=learner.nickname if learner else "",
        content=row.content,
        level=row.level,
        level_label=LEVEL_LABEL.get(row.level, row.level),
        read_by_learner=row.read_by_learner,
        created_at=row.created_at.isoformat() if row.created_at else None,
        scenario_name=record.scenario_name if record else "",
        score_total=record.score_total if record else 0,
    )


async def teacher_can_access(
    session: AsyncSession, teacher: Account, learner_id: uuid.UUID
) -> bool:
    """教师是否有权操作该学员的数据。管理员恒为真。"""
    if teacher.role == Role.ADMIN.value:
        return True
    target = await session.get(Account, learner_id)
    if target is None:
        return False
    return target.teacher_id == teacher.id


async def create_comment(
    session: AsyncSession,
    author: Account,
    *,
    record_id: uuid.UUID,
    content: str,
    level: str,
) -> CommentOut:
    """写点评。记录必须存在，且作者对其学员有权限。"""
    record = await session.get(TrainingRecord, record_id)
    if record is None:
        raise AppError.not_found("训练记录不存在")

    if not await teacher_can_access(session, author, record.owner_id):
        raise AppError.forbidden("只能点评自己名下学员的记录")

    text = content.strip()
    if not text:
        raise AppError.bad_request("点评内容不能为空")

    row = TeacherComment(
        record_id=record_id,
        teacher_id=author.id,
        learner_id=record.owner_id,
        content=text,
        level=level,
    )
    session.add(row)
    # 必须显式 commit：get_session 只在异常时 rollback，成功路径不提交。
    # 只 flush 的话请求返回 200 但数据在会话关闭时丢失（曾踩到）。
    await session.flush()
    await session.commit()

    learner = await session.get(Account, record.owner_id)
    return _to_out(row, author, learner, record)


async def list_by_record(
    session: AsyncSession, account: Account, record_id: uuid.UUID
) -> CommentListOut:
    """某条记录下的全部点评。学员本人、其教师、管理员可见。"""
    record = await session.get(TrainingRecord, record_id)
    if record is None:
        raise AppError.not_found("训练记录不存在")

    is_owner = record.owner_id == account.id
    if not is_owner:
        allowed = account.role == Role.ADMIN.value or await teacher_can_access(
            session, account, record.owner_id
        )
        if not allowed:
            raise AppError.forbidden("无权查看该记录的点评")

    rows = (
        await session.execute(
            select(TeacherComment)
            .where(TeacherComment.record_id == record_id)
            .order_by(TeacherComment.created_at.desc())
        )
    ).scalars().all()

    teacher_ids = {r.teacher_id for r in rows}
    learner = await session.get(Account, record.owner_id)
    teachers: dict[uuid.UUID, Account] = {}
    if teacher_ids:
        found = await session.execute(
            select(Account).where(Account.id.in_(teacher_ids))
        )
        teachers = {a.id: a for a in found.scalars()}

    items = [
        _to_out(r, teachers.get(r.teacher_id), learner, record) for r in rows
    ]
    return CommentListOut(items=items, total=len(items), unread=0)


async def list_for_learner(
    session: AsyncSession, account: Account, learner_id: uuid.UUID
) -> CommentListOut:
    """某学员收到的全部点评。

    学员本人查看时会顺带把未读标记为已读——这是"学生端提示有新点评"
    能生效的前提，否则会一直显示有未读。
    """
    is_self = learner_id == account.id
    if not is_self:
        allowed = account.role == Role.ADMIN.value or await teacher_can_access(
            session, account, learner_id
        )
        if not allowed:
            raise AppError.forbidden("无权查看该学员的点评")

    stmt = (
        select(TeacherComment)
        .where(TeacherComment.learner_id == learner_id)
        .order_by(TeacherComment.created_at.desc())
    )
    # 教师只看自己写的？不——教师应看到该学员收到的全部点评，
    # 便于了解前任教师/其他教师给过什么反馈，避免重复或矛盾。
    rows = (await session.execute(stmt)).scalars().all()

    record_ids = {r.record_id for r in rows}
    records: dict[uuid.UUID, TrainingRecord] = {}
    if record_ids:
        found = await session.execute(
            select(TrainingRecord).where(TrainingRecord.id.in_(record_ids))
        )
        records = {t.id: t for t in found.scalars()}

    teacher_ids = {r.teacher_id for r in rows}
    teachers: dict[uuid.UUID, Account] = {}
    if teacher_ids:
        found = await session.execute(
            select(Account).where(Account.id.in_(teacher_ids))
        )
        teachers = {a.id: a for a in found.scalars()}

    learner = await session.get(Account, learner_id)
    unread = sum(1 for r in rows if not r.read_by_learner)

    # 学员本人查看即视为已读
    if is_self and unread:
        for r in rows:
            r.read_by_learner = True
        await session.commit()

    items = [
        _to_out(r, teachers.get(r.teacher_id), learner, records.get(r.record_id))
        for r in rows
    ]
    return CommentListOut(items=items, total=len(items), unread=unread)


async def unread_count(
    session: AsyncSession, account: Account
) -> int:
    """学员未读点评数，用于顶栏红点。"""
    return int(
        (
            await session.execute(
                select(func.count(TeacherComment.id)).where(
                    TeacherComment.learner_id == account.id,
                    TeacherComment.read_by_learner.is_(False),
                )
            )
        ).scalar_one()
        or 0
    )


async def delete_comment(
    session: AsyncSession, account: Account, comment_id: uuid.UUID
) -> None:
    """删除点评。只有作者本人或管理员可删。"""
    row = await session.get(TeacherComment, comment_id)
    if row is None:
        raise AppError.not_found("点评不存在")
    if row.teacher_id != account.id and account.role != Role.ADMIN.value:
        raise AppError.forbidden("只能删除自己写的点评")
    await session.delete(row)
    await session.commit()
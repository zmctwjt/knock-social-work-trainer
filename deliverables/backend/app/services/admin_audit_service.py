"""管理操作审计。

设计原则：
1. **失败不影响主流程** —— 审计是旁路，写日志出错不能让"停用账号"失败。
   所有写操作包 try/except 并只记 warning。
2. **不落敏感明文** —— 摘要里出现的口令、令牌一律替换为 ***。
3. **目标可回溯** —— target_type + target_id 能串起某个对象的完整变更链。
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Account, AdminAuditLog

log = structlog.get_logger(__name__)

#: 可能出现敏感值的键，写摘要前统一打码
_SENSITIVE_KEYS = {"password", "passwd", "token", "secret", "api_key", "glm_api_key"}


def _mask(payload: dict[str, Any] | None) -> str:
    """把变更字段拼成可读摘要并打码敏感值。"""
    if not payload:
        return ""
    parts: list[str] = []
    for key, value in payload.items():
        if key.lower() in _SENSITIVE_KEYS:
            parts.append(f"{key}=***")
            continue
        text = "" if value is None else str(value)
        if len(text) > 60:
            text = text[:57] + "..."
        parts.append(f"{key}={text}")
    return " ".join(parts)[:255]


async def record(
    session: AsyncSession,
    *,
    actor: Account | None,
    action: str,
    target_type: str = "",
    target_id: str | uuid.UUID = "",
    payload: dict[str, Any] | None = None,
    summary: str | None = None,
    request_id: str = "",
) -> None:
    """写一条审计。**永不抛异常**，失败只记 warning。"""
    try:
        row = AdminAuditLog(
            actor_id=actor.id if actor else None,
            actor_name=actor.nickname if actor else "系统",
            actor_role=actor.role if actor else "",
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            summary=(summary if summary is not None else _mask(payload))[:255],
            request_id=request_id,
        )
        session.add(row)
        # 必须 commit：get_session 成功路径不提交，只 flush 会在会话关闭时丢失。
        # 审计在业务提交之后调用，此处提交不会影响业务事务。
        await session.commit()
    except Exception as exc:  # noqa: BLE001 —— 审计失败不能影响业务
        log.warning("admin_audit_failed", action=action, error=str(exc))


async def list_logs(
    session: AsyncSession,
    *,
    limit: int = 50,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """按时间倒序查审计。"""
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AdminAuditLog.actor_id == actor_id)
    rows = (await session.execute(stmt.limit(max(1, min(limit, 500))))).scalars().all()

    items = [
        {
            "id": str(r.id),
            "actor_name": r.actor_name,
            "actor_role": r.actor_role,
            "action": r.action,
            "action_label": ACTION_LABEL.get(r.action, r.action),
            "target_type": r.target_type,
            "target_id": r.target_id,
            "summary": r.summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


#: 动作码 → 中文标签，前端直接展示
ACTION_LABEL = {
    "account.create": "新建账号",
    "account.toggle": "启停账号",
    "account.bulk_active": "批量启停",
    "scenario.upsert": "保存案例",
    "scenario.archive": "下架案例",
    "card.upsert": "保存技巧卡",
    "card.delete": "删除技巧卡",
    "rule_word.add": "追加词条",
    "rule_word.disable": "禁用词条",
    "rule_word.delete": "删除词条",
    "script_line.add": "新增台词",
    "script_line.delete": "删除台词",
    "comment.create": "发布点评",
    "comment.delete": "删除点评",
}

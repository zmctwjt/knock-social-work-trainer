"""FastAPI 依赖：当前用户、角色校验、客户端 IP、应用级单例。

认证链路：`Authorization: Bearer <access token>` → 验签 → 校验类型/iss →
查撤销表 → 查账号 → 写入 `user_id_hash` 日志上下文。任何一步失败都是 40101。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.context import set_user_id_hash
from app.core.errors import AppError
from app.core.middleware import get_client_ip
from app.core.security import decode_token, hash_account_id
from app.domain.enums import Role, TokenType
from app.domain.models import Account, TokenRevocation
from app.infra.db import Database
from app.infra.redis import KVStore
from app.infra.session import get_session

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_settings_from(request: Request) -> Settings:
    settings: Settings | None = getattr(request.app.state, "settings", None)
    if settings is None:  # pragma: no cover
        raise RuntimeError("app.state.settings 未初始化")
    return settings


def get_store(request: Request) -> KVStore:
    store: KVStore | None = getattr(request.app.state, "store", None)
    if store is None:  # pragma: no cover
        raise RuntimeError("app.state.store 未初始化")
    return store


def get_db(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "db", None)
    if database is None:  # pragma: no cover
        raise RuntimeError("app.state.db 未初始化")
    return database


SettingsDep = Annotated[Settings, Depends(get_settings_from)]
StoreDep = Annotated[KVStore, Depends(get_store)]
DatabaseDep = Annotated[Database, Depends(get_db)]


async def _load_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    account = await session.get(Account, account_id)
    if account is None:
        raise AppError.unauthorized("账号不存在或已注销")
    if not account.is_active:
        raise AppError.forbidden("账号已被停用")
    return account


async def _is_revoked(session: AsyncSession, jti: str) -> bool:
    result = await session.execute(select(TokenRevocation.id).where(TokenRevocation.jti == jti))
    return result.scalar_one_or_none() is not None


async def get_current_user(
    request: Request,
    credentials: CredentialsDep,
    settings: SettingsDep,
    session: SessionDep,
) -> Account:
    if credentials is None or not credentials.credentials:
        raise AppError.unauthorized()

    claims = decode_token(
        credentials.credentials,
        expected_type=TokenType.ACCESS,
        settings=settings,
    )

    jti = str(claims.get("jti", ""))
    if jti and await _is_revoked(session, jti):
        raise AppError.unauthorized("令牌已失效，请重新登录")

    try:
        account_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise AppError.unauthorized("令牌载荷不完整") from exc

    account = await _load_account(session, account_id)
    set_user_id_hash(hash_account_id(account.id))
    request.state.account_id = account.id
    return account


async def get_optional_user(
    request: Request,
    credentials: CredentialsDep,
    settings: SettingsDep,
    session: SessionDep,
) -> Account | None:
    """匿名可访问的接口用它：有 token 就解析，没有也不报错。"""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_current_user(request, credentials, settings, session)
    except AppError:
        return None


CurrentUser = Annotated[Account, Depends(get_current_user)]
OptionalUser = Annotated[Account | None, Depends(get_optional_user)]


def require_roles(*roles: Role) -> Callable:
    """角色守卫（RBAC 矩阵见第 5 章表 5-6）。"""
    allowed = {role.value for role in roles}

    async def dependency(user: CurrentUser) -> Account:
        if user.role not in allowed:
            raise AppError.forbidden("当前角色无权执行该操作")
        return user

    return dependency


async def require_human(user: CurrentUser) -> Account:
    """写操作守卫：游客账号为只读体验，创建会话/提交发言一律拒绝。"""
    if user.is_guest:
        raise AppError.forbidden("游客账号为只读体验，请注册后创建训练")
    return user


async def require_admin(user: CurrentUser) -> Account:
    if user.role != Role.ADMIN.value:
        raise AppError.forbidden("需要管理员角色")
    return user


HumanUser = Annotated[Account, Depends(require_human)]
AdminUser = Annotated[Account, Depends(require_admin)]


def client_ip(request: Request) -> str:
    return get_client_ip(request)

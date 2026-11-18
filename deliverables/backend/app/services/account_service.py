"""账号服务：登录、游客、刷新、令牌撤销。

三条安全约定：
1. 登录失败一律回同一句话（40101），不区分"用户不存在"与"密码错误"，
   避免被用来枚举账号；
2. 刷新令牌**一次性**：用掉即写入撤销表，换发新的一对；
3. 游客账号有独立角色 `guest` 且 `is_guest=True`，写操作在依赖层被拒。
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    decode_token,
    hash_password,
    hash_token,
    issue_token_pair,
    verify_password,
)
from app.domain.enums import Role, TokenType
from app.domain.models import Account, TokenRevocation
from app.domain.schemas import AccountOut, GuestOut, LoginOut, TokenPair

BAD_CREDENTIALS = "用户名或密码错误"


async def authenticate(session: AsyncSession, username: str, password: str, settings: Settings) -> Account:
    account = (
        await session.execute(select(Account).where(Account.username == username))
    ).scalar_one_or_none()
    if account is None:
        # 仍做一次哈希校验，避免用响应时间判断账号是否存在
        verify_password(password, hash_password("dummy-password-for-timing", settings), settings)
        raise AppError.unauthorized(BAD_CREDENTIALS)
    if not verify_password(password, account.password_hash, settings):
        raise AppError.unauthorized(BAD_CREDENTIALS)
    if not account.is_active:
        raise AppError.forbidden("账号已被停用，请联系管理员")
    return account


def _account_out(account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        username=account.username,
        nickname=account.nickname,
        role=Role(account.role),
        is_guest=account.is_guest,
        created_at=account.created_at,
    )


def _pair(account: Account, settings: Settings) -> TokenPair:
    payload = issue_token_pair(
        account_id=account.id,
        role=Role(account.role),
        is_guest=account.is_guest,
        settings=settings,
    )
    return TokenPair(**payload)


async def create_account(
    session: AsyncSession,
    settings: Settings,
    *,
    username: str,
    password: str,
    nickname: str | None = None,
    role: Role = Role.STUDENT,
) -> Account:
    """创建账号（幂等）：供初始化脚本、测试夹具与后台导入使用。

    生产环境不开放自助注册，账号由教务/督导统一导入——这是毕设场景的
    真实约束，也避免把注册接口暴露在公网后被刷号。
    """
    existing = (
        await session.execute(select(Account).where(Account.username == username))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    account = Account(
        id=uuid.uuid4(),
        username=username,
        nickname=nickname or username,
        password_hash=hash_password(password, settings),
        role=role.value if isinstance(role, Role) else str(role),
        is_guest=False,
        is_active=True,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def login(session: AsyncSession, settings: Settings, username: str, password: str) -> LoginOut:
    account = await authenticate(session, username, password, settings)
    account.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    return LoginOut(account=_account_out(account), tokens=_pair(account, settings))


async def create_guest(session: AsyncSession, settings: Settings, nickname: str | None = None) -> GuestOut:
    suffix = secrets.token_hex(4)
    account = Account(
        id=uuid.uuid4(),
        username=f"guest_{suffix}",
        nickname=(nickname or f"游客{suffix[:4]}")[:32],
        password_hash=hash_password(secrets.token_urlsafe(24), settings),
        role=Role.GUEST.value,
        is_guest=True,
        is_active=True,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return GuestOut(account=_account_out(account), tokens=_pair(account, settings))


async def _revoke(session: AsyncSession, *, jti: str, account_id: uuid.UUID, token_type: TokenType, reason: str, expires_at: datetime) -> None:
    existing = (
        await session.execute(select(TokenRevocation.id).where(TokenRevocation.jti == jti))
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        TokenRevocation(
            jti=jti,
            account_id=account_id,
            token_type=token_type.value,
            reason=reason,
            expires_at=expires_at,
        )
    )


async def refresh_tokens(session: AsyncSession, settings: Settings, refresh_token: str) -> TokenPair:
    claims = decode_token(refresh_token, expected_type=TokenType.REFRESH, settings=settings)
    jti = str(claims.get("jti", ""))
    if not jti:
        raise AppError.unauthorized("刷新令牌缺少 jti")

    revoked = (
        await session.execute(select(TokenRevocation.id).where(TokenRevocation.jti == jti))
    ).scalar_one_or_none()
    if revoked is not None:
        raise AppError.unauthorized("刷新令牌已使用或已撤销，请重新登录")

    try:
        account_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise AppError.unauthorized("刷新令牌载荷不完整") from exc

    account = await session.get(Account, account_id)
    if account is None or not account.is_active:
        raise AppError.unauthorized("账号不存在或已停用")

    # 轮换：旧 refresh 立即作废，缩小泄漏窗口
    exp = datetime.fromtimestamp(int(claims.get("exp", 0)), tz=timezone.utc)
    await _revoke(
        session,
        jti=jti,
        account_id=account.id,
        token_type=TokenType.REFRESH,
        reason="rotated",
        expires_at=exp or (datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_ttl_days)),
    )
    await session.commit()
    return _pair(account, settings)


async def logout(session: AsyncSession, account: Account, access_token: str, settings: Settings) -> None:
    """登出只撤销当前 access；refresh 由过期或轮换兜底。"""
    try:
        claims = decode_token(access_token, expected_type=TokenType.ACCESS, settings=settings)
    except AppError:
        return
    jti = str(claims.get("jti", ""))
    if not jti:
        return
    exp = datetime.fromtimestamp(int(claims.get("exp", 0)), tz=timezone.utc)
    await _revoke(
        session,
        jti=jti,
        account_id=account.id,
        token_type=TokenType.ACCESS,
        reason="logout",
        expires_at=exp,
    )
    await session.commit()


async def revoke_token_value(session: AsyncSession, token: str, settings: Settings, reason: str) -> None:
    """按 token 原文撤销（测试与运维工具用）。"""
    claims = decode_token(token, expected_type=None, settings=settings)
    account_id = uuid.UUID(str(claims["sub"]))
    await _revoke(
        session,
        jti=str(claims.get("jti", hash_token(token)[:16])),
        account_id=account_id,
        token_type=TokenType(claims.get("typ", "access")),
        reason=reason,
        expires_at=datetime.fromtimestamp(int(claims.get("exp", 0)), tz=timezone.utc),
    )
    await session.commit()

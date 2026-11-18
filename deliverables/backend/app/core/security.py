"""认证原语：Argon2id 口令哈希 + PyJWT 双令牌。

设计取舍：
- 口令哈希参数写入环境变量（`ARGON2_*`），生产环境按 64 MiB / t=3 起步；
- access token 30 分钟，refresh token 7 天，均带 `jti`。撤销不靠改密钥，
  而是把 `jti` 写入 `token_revocations` 表——改密钥会让全部在线会话失效；
- 游客 token 24 小时，`is_guest=True`，服务层据此拒绝写操作。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domain.enums import Role, TokenType

ISSUER = "knock-backend"


#: 默认开发密钥。生产环境启动时会被 `Settings.production_errors` 拒绝。
DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me-please-32bytes"


@lru_cache(maxsize=4)
def _hasher(time_cost: int, memory_cost: int, parallelism: int) -> PasswordHasher:
    return PasswordHasher(
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=32,
        salt_len=16,
    )


def _password_hasher(settings: Settings | None = None) -> PasswordHasher:
    cfg = settings or get_settings()
    return _hasher(cfg.argon2_time_cost, cfg.argon2_memory_cost, cfg.argon2_parallelism)


def hash_password(password: str, settings: Settings | None = None) -> str:
    return _password_hasher(settings).hash(password)


def verify_password(password: str, password_hash: str, settings: Settings | None = None) -> bool:
    """校验口令。任何 Argon2 异常都视为校验失败，不向调用方泄露细节。"""
    if not password or not password_hash:
        return False
    try:
        return _password_hasher(settings).verify(password_hash, password)
    except Argon2Error:
        return False


def needs_rehash(password_hash: str, settings: Settings | None = None) -> bool:
    try:
        return _password_hasher(settings).check_needs_rehash(password_hash)
    except Argon2Error:
        return True


# ═══════════════════════════════════════════════════════════
# JWT
# ═══════════════════════════════════════════════════════════


def _now() -> datetime:
    return datetime.now(timezone.utc)


def encode_token(
    *,
    account_id: uuid.UUID | str,
    role: Role,
    token_type: TokenType,
    ttl_seconds: int,
    settings: Settings | None = None,
    is_guest: bool = False,
) -> tuple[str, str, datetime]:
    """签发令牌，返回 `(token, jti, 过期时间)`。"""
    cfg = settings or get_settings()
    now = _now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(account_id),
        "role": role.value,
        "typ": token_type.value,
        "jti": jti,
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "guest": is_guest,
    }
    token = jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)
    return token, jti, expires_at


def issue_token_pair(
    *,
    account_id: uuid.UUID | str,
    role: Role,
    is_guest: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """签发 access + refresh 双令牌。游客使用 24 小时短期 access。"""
    cfg = settings or get_settings()
    if is_guest:
        access, _, _ = encode_token(
            account_id=account_id,
            role=role,
            token_type=TokenType.ACCESS,
            ttl_seconds=cfg.guest_ttl_seconds,
            settings=cfg,
            is_guest=True,
        )
        refresh, _, _ = encode_token(
            account_id=account_id,
            role=role,
            token_type=TokenType.REFRESH,
            ttl_seconds=cfg.guest_ttl_seconds,
            settings=cfg,
            is_guest=True,
        )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": cfg.guest_ttl_seconds,
            "role": role,
            "is_guest": True,
        }

    access, _, _ = encode_token(
        account_id=account_id,
        role=role,
        token_type=TokenType.ACCESS,
        ttl_seconds=cfg.access_ttl_seconds,
        settings=cfg,
    )
    refresh, _, _ = encode_token(
        account_id=account_id,
        role=role,
        token_type=TokenType.REFRESH,
        ttl_seconds=cfg.refresh_ttl_seconds,
        settings=cfg,
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": cfg.access_ttl_seconds,
        "role": role,
        "is_guest": False,
    }


def decode_token(
    token: str,
    *,
    expected_type: TokenType | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """解析并校验令牌；失败统一抛 40101，不区分"过期"与"伪造"。"""
    cfg = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            cfg.jwt_secret,
            algorithms=[cfg.jwt_algorithm],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "jti", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError.unauthorized("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError.unauthorized("令牌无效") from exc

    if expected_type is not None and claims.get("typ") != expected_type.value:
        raise AppError.unauthorized("令牌类型不匹配")
    return claims


def identify_token(token: str) -> TokenType | None:
    """不验签地读取 `typ`，仅用于让刷新接口给出更准确的错误信息。"""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return None
    raw = claims.get("typ")
    try:
        return TokenType(raw)
    except ValueError:
        return None


def hash_token(token: str) -> str:
    """日志与黑名单定位用的短哈希，避免明文令牌落盘。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def hash_account_id(account_id: uuid.UUID | str) -> str:
    """日志里的用户标识：不可逆哈希，满足"能串联、不能识别"的要求。"""
    return hashlib.sha256(str(account_id).encode("utf-8")).hexdigest()[:16]

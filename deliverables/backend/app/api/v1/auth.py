"""认证接口：登录、刷新、游客、当前用户、登出。

令牌策略与旧前端契约一致：access 30 分钟、refresh 7 天、游客 24 小时；
刷新采用「轮换 + 撤销」——旧 refresh 用过即废，降低令牌被重放的概率。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import auth_rate_limit
from app.core.deps import CredentialsDep, CurrentUser, SessionDep, SettingsDep
from app.core.errors import AppError
from app.core.response import ok
from app.domain.schemas import (
    AccountOut,
    Envelope,
    GuestOut,
    GuestRequest,
    LoginOut,
    LoginRequest,
    MessageOut,
    RefreshRequest,
    TokenPair,
)
from app.services import account_service

router = APIRouter(
    prefix="/auth",
    tags=["认证"],
    dependencies=[Depends(auth_rate_limit)],
)


@router.post("/login", response_model=Envelope[LoginOut], summary="账号密码登录")
async def login(payload: LoginRequest, session: SessionDep, settings: SettingsDep):
    result = await account_service.login(
        session, settings, payload.username, payload.password
    )
    return ok(result, message="登录成功")


@router.post("/refresh", response_model=Envelope[TokenPair], summary="刷新访问令牌")
async def refresh(payload: RefreshRequest, session: SessionDep, settings: SettingsDep):
    pair = await account_service.refresh_tokens(session, settings, payload.refresh_token)
    return ok(pair, message="令牌已刷新")


@router.post("/guest", response_model=Envelope[GuestOut], summary="创建游客账号")
async def guest(payload: GuestRequest, session: SessionDep, settings: SettingsDep):
    result = await account_service.create_guest(session, settings, payload.nickname)
    return ok(result, message="游客账号已创建")


@router.get("/me", response_model=Envelope[AccountOut], summary="读取当前账号")
async def me(account: CurrentUser):
    return ok(AccountOut.model_validate(account))


@router.post("/logout", response_model=Envelope[MessageOut], summary="登出并撤销令牌")
async def logout(
    request: Request,
    account: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    credentials: CredentialsDep,
):
    if credentials is None:
        raise AppError.unauthorized()
    raw = request.headers.get("authorization", "")
    token = raw.split(" ", 1)[1] if " " in raw else credentials.credentials
    await account_service.logout(session, account, token, settings)
    return ok(MessageOut(message="已登出"), message="已登出")

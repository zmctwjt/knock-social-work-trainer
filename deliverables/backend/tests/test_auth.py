"""认证：登录、失败、刷新轮换、游客权限、令牌校验。"""

from __future__ import annotations

from app.core.security import encode_token
from app.domain.enums import Role, TokenType
from tests.helpers import PASSWORD, auth, login, seed_account


async def test_login_success_returns_token_pair(app, client):
    await seed_account(app)
    data = await login(client)
    assert data["account"]["username"] == "stu1"
    assert data["tokens"]["access_token"]
    assert data["tokens"]["role"] == "student"
    assert data["tokens"]["expires_in"] >= 60


async def test_login_wrong_password_returns_40101(app, client):
    await seed_account(app)
    response = await client.post(
        "/api/v1/auth/login", json={"username": "stu1", "password": "wrong-pass"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == 40101
    assert "用户名或密码错误" in response.json()["message"]


async def test_login_unknown_user_uses_same_message(app, client):
    response = await client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "whatever1"}
    )
    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码错误"


async def test_me_requires_and_returns_account(app, client):
    await seed_account(app)
    tokens = (await login(client))["tokens"]
    response = await client.get("/api/v1/auth/me", headers=auth(tokens["access_token"]))
    assert response.status_code == 200
    assert response.json()["data"]["username"] == "stu1"

    anonymous = await client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == 40101


async def test_refresh_rotates_and_revokes_old_token(app, client):
    await seed_account(app)
    tokens = (await login(client))["tokens"]

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200
    new_tokens = first.json()["data"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == 40101


async def test_logout_revokes_access_token(app, client):
    await seed_account(app)
    tokens = (await login(client))["tokens"]
    headers = auth(tokens["access_token"])
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    out = await client.post("/api/v1/auth/logout", headers=headers)
    assert out.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_guest_can_read_but_not_write(app, client):
    guest = await client.post("/api/v1/auth/guest", json={"nickname": "体验者"})
    assert guest.status_code == 200
    data = guest.json()["data"]
    assert data["tokens"]["is_guest"] is True
    headers = auth(data["tokens"]["access_token"])

    assert (await client.get("/api/v1/scenarios", headers=headers)).status_code == 200

    created = await client.post(
        "/api/v1/sessions", json={"scenario_id": "W-01"}, headers=headers
    )
    assert created.status_code == 403
    assert created.json()["code"] == 40301


async def test_expired_access_token_rejected(app, client):
    account = await seed_account(app)
    settings = app.state.settings
    token, _jti, _exp = encode_token(
        account_id=account.id,
        role=Role.STUDENT,
        token_type=TokenType.ACCESS,
        ttl_seconds=-10,
        settings=settings,
        is_guest=False,
    )
    response = await client.get("/api/v1/auth/me", headers=auth(token))
    assert response.status_code == 401
    assert response.json()["code"] == 40101


async def test_refresh_token_cannot_be_used_as_access(app, client):
    await seed_account(app)
    tokens = (await login(client))["tokens"]
    response = await client.get(
        "/api/v1/auth/me", headers=auth(tokens["refresh_token"])
    )
    assert response.status_code == 401


async def test_disabled_account_cannot_login(app, client):
    account = await seed_account(app)
    async with app.state.db.session() as session:
        from app.domain.models import Account

        row = await session.get(Account, account.id)
        row.is_active = False
    response = await client.post(
        "/api/v1/auth/login", json={"username": "stu1", "password": PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["code"] == 40301

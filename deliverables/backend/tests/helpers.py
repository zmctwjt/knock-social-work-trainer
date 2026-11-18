"""测试通用动作：建账号、登录、拿 token、建会话。"""

from __future__ import annotations

from app.domain.enums import Role
from app.services import account_service

PASSWORD = "Passw0rd!2026"


async def seed_account(
    application,
    *,
    username: str = "stu1",
    nickname: str = "学员一",
    role: Role = Role.STUDENT,
    password: str = PASSWORD,
):
    async with application.state.db.session() as session:
        return await account_service.create_account(
            session,
            application.state.settings,
            username=username,
            password=password,
            nickname=nickname,
            role=role,
        )


async def login(client, username: str = "stu1", password: str = PASSWORD) -> dict:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_session(client, headers: dict, **payload) -> dict:
    body = {"scenario_id": "W-01", **payload}
    response = await client.post("/api/v1/sessions", json=body, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return data


async def submit_turn(client, headers: dict, session_id: str, text: str, **extra) -> dict:
    response = await client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"text": text, **extra},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


__all__ = [
    "PASSWORD",
    "auth",
    "create_session",
    "login",
    "seed_account",
    "submit_turn",
]

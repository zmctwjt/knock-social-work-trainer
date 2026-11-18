"""MySQL 端到端冒烟：建演示账号 -> 登录 -> 建会话 -> 发言 -> 分段评分 -> 结案 -> 统计。

用法（在 deliverables/backend 下）：python ../../work/smoke_mysql.py
"""
from __future__ import annotations

import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8000"


async def ensure_account() -> None:
    sys.path.insert(0, ".")
    from app.core.config import get_settings
    from app.domain.enums import Role
    from app.infra.db import Database
    from app.services.account_service import create_account

    settings = get_settings()
    db = Database(settings)
    await db.connect()
    try:
        async with db.session() as session:
            await create_account(
                session,
                settings,
                username="demo_student",
                password="Demo@12345",
                nickname="演示学生",
                role=Role.STUDENT,
            )
    finally:
        await db.disconnect()


async def main() -> int:
    await ensure_account()
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        r = await c.post("/api/v1/auth/login", json={"username": "demo_student", "password": "Demo@12345"})
        r.raise_for_status()
        token = r.json()["data"]["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = await c.get("/api/v1/scenarios", headers=headers)
        scenarios = r.json()["data"]["items"]
        print(f"scenarios={len(scenarios)} first={scenarios[0]['id']}")

        r = await c.post(
            "/api/v1/sessions",
            headers=headers,
            json={"scenario_id": "W-01", "max_turns": 40},
        )
        r.raise_for_status()
        sid = r.json()["data"]["id"]
        print(f"session={sid}")

        turns = [
            "王阿姨您好，我是社区的小陈。今天来是想陪您聊聊最近的情况，您方便吗？",
            "听起来这段时间您一个人扛了很多，能跟我说说最难受的是什么时候吗？",
        ]
        for text in turns:
            r = await c.post(f"/api/v1/sessions/{sid}/turns", headers=headers, json={"text": text})
            if r.status_code != 200:
                print("turn failed", r.status_code, r.text[:300])
                return 1
            pair = r.json()["data"]
            print(f"turn ok speaker={pair['client']['speaker']} source={pair['client']['source']}")

        r = await c.post(f"/api/v1/sessions/{sid}/stages/1/score", headers=headers)
        print("score", r.status_code, str(r.json()["data"])[:160] if r.status_code == 200 else r.text[:200])

        r = await c.post(f"/api/v1/sessions/{sid}/finish", headers=headers)
        print("finish", r.status_code, str(r.json().get("data"))[:200] if r.status_code == 200 else r.text[:200])

        for path in ("/api/v1/stats/me", "/api/v1/stats/heatmap", "/api/v1/sessions"):
            r = await c.get(path, headers=headers)
            body = r.json().get("data") if r.status_code == 200 else r.text[:200]
            print(path, r.status_code, str(body)[:180])

        r = await c.get("/api/v1/auth/me", headers=headers)
        print("me", r.status_code, r.json()["data"]["username"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

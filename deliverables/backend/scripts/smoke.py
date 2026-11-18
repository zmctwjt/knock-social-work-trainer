"""端到端冒烟脚本：不依赖外部 PG/Redis，直接驱动 ASGI 应用。

用法：
    python scripts/smoke.py
覆盖：存活/就绪探针、案例目录、登录、创建会话、发言（无 key 时规则降级）、统计。
任何一步失败即以非 0 退出，可放进 CI 或部署后自检。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")          # 内存库
os.environ.setdefault("AUTO_CREATE_SCHEMA", "true")
os.environ.setdefault("SEED_SCENARIOS_ON_STARTUP", "true")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("GLM_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "smoke-secret-0123456789abcdef0123456789")

import httpx  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.domain.enums import Role  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.account_service import create_account  # noqa: E402


async def run() -> int:
    settings = Settings(_env_file=None)
    application = create_app(settings)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
            response = await client.get("/healthz")
            check("GET /healthz", response.status_code == 200, f"http={response.status_code}")

            response = await client.get("/readyz")
            check("GET /readyz", response.status_code == 200, f"http={response.status_code}")

            response = await client.get("/metrics")
            check(
                "GET /metrics",
                response.status_code == 200 and "http_requests_total" in response.text,
                f"http={response.status_code}",
            )

            response = await client.get("/api/v1/scenarios")
            body = response.json()
            total = body["data"]["total"]
            check("GET /api/v1/scenarios", total == 12, f"total={total}")

            async with application.state.db.session() as session:
                await create_account(
                    session,
                    settings,
                    username="smoke",
                    password="Passw0rd!2026",
                    nickname="冒烟账号",
                    role=Role.STUDENT,
                )

            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "smoke", "password": "Passw0rd!2026"},
            )
            login = response.json()
            token = login["data"]["tokens"]["access_token"]
            check("POST /api/v1/auth/login", response.status_code == 200, f"role={login['data']['account']['role']}")
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                "/api/v1/sessions", json={"scenario_id": "W-01"}, headers=headers
            )
            session_id = response.json()["data"]["id"]
            check("POST /api/v1/sessions", response.status_code == 200, f"id={session_id[:8]}…")

            response = await client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"text": "王阿姨，最近睡得好吗？"},
                headers=headers,
            )
            turn = response.json()["data"]
            check(
                "POST /api/v1/sessions/{id}/turns",
                response.status_code == 200 and bool(turn["client"]["text"]),
                f"degraded={turn['client']['degraded']}",
            )

            response = await client.post(
                f"/api/v1/sessions/{session_id}/finish", headers=headers
            )
            check("POST /api/v1/sessions/{id}/finish", response.status_code == 200)

            response = await client.get("/api/v1/stats/me", headers=headers)
            stats = response.json()["data"]
            check(
                "GET /api/v1/stats/me",
                stats["total_sessions"] == 1,
                f"turns={stats['total_turns']}",
            )

            response = await client.get("/api/health")
            legacy = response.json()
            check(
                "GET /api/health（旧版）",
                response.status_code == 200 and legacy["ok"] is True,
                f"model={legacy['ai']['model']}",
            )

    failed = [name for name, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

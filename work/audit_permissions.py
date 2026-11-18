"""权限矩阵端到端验证：四角色 × 关键接口，逐个断言期望状态码。

这是上线前的"权限体检"：不依赖单测的 mock，直接打真实服务与真实 MySQL。
用法（服务已在 8000 运行时）：
    work\\pyenv\\Scripts\\python.exe work\\audit_permissions.py
退出码 0 表示全部符合预期。
"""

from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"
PASSWORD = "Audit@12345"

#: 角色 → 账号名（需提前用脚本创建，见 ensure_accounts）
ACCOUNTS = {
    "guest": None,  # 游客走 /auth/guest 动态创建
    "student": "audit_stu",
    "teacher": "audit_tea",
    "admin": "audit_adm",
}

OK, DENY, AUTH_FAIL = 200, 403, 40301  # 40301 是整数错误码
FAILURES: list[str] = []


def check(label: str, actual: object, expected: object) -> None:
    status = "PASS" if actual == expected else "FAIL"
    if status == "FAIL":
        FAILURES.append(f"{label}: 期望 {expected}，实际 {actual}")
    print(f"  [{status}] {label:52s} {actual}")


async def ensure_accounts() -> None:
    """建四个角色的审计账号（幂等）。"""
    import asyncio
    import os
    import sys as _sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent / "deliverables" / "backend"
    _sys.path.insert(0, str(backend))
    os.chdir(backend)

    from app.core.config import get_settings
    from app.domain.enums import Role
    from app.infra.db import Database
    from app.services.account_service import create_account

    settings = get_settings()
    db = Database(settings)
    await db.connect()
    try:
        async with db.session() as session:
            for role, name in (
                (Role.STUDENT, ACCOUNTS["student"]),
                (Role.TEACHER, ACCOUNTS["teacher"]),
                (Role.ADMIN, ACCOUNTS["admin"]),
            ):
                await create_account(
                    session, settings, username=name, password=PASSWORD,
                    nickname=f"审计-{role.value}", role=role,
                )
    finally:
        await db.disconnect()
    await asyncio.sleep(0)


def login(client: httpx.Client, username: str) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["data"]["tokens"]["access_token"]


def main() -> int:
    import asyncio

    asyncio.run(ensure_accounts())

    with httpx.Client(base_url=BASE, timeout=20) as c:
        tokens = {
            "student": login(c, ACCOUNTS["student"]),
            "teacher": login(c, ACCOUNTS["teacher"]),
            "admin": login(c, ACCOUNTS["admin"]),
        }
        guest = c.post("/api/v1/auth/guest", json={"nickname": "审计路人"})
        tokens["guest"] = guest.json()["data"]["tokens"]["access_token"]

        H = lambda role: {"Authorization": f"Bearer {tokens[role]}"}  # noqa: E731

        print("\n=== 公开接口（任何角色都可读）===")
        for path in ("/api/v1/scenarios", "/api/v1/knowledge/cards"):
            for role in ("guest", "student", "teacher", "admin"):
                check(f"{role} GET {path}", c.get(path, headers=H(role)).status_code, OK)

        print("\n=== 训练写入：游客禁止，其余允许 ===")
        for role in ("guest", "student", "teacher", "admin"):
            r = c.post("/api/v1/sessions", headers=H(role), json={"scenario_id": "W-01"})
            check(f"{role} POST /sessions", r.status_code, DENY if role == "guest" else OK)
            if role == "guest":
                check(f"{role} POST /sessions 错误码", r.json()["code"], AUTH_FAIL)

        print("\n=== 教师端：学生禁止，教师/管理员允许 ===")
        for role in ("guest", "student", "teacher", "admin"):
            for path in ("/api/v1/teacher/learners", "/api/v1/teacher/stats"):
                r = c.get(path, headers=H(role))
                expect = OK if role in ("teacher", "admin") else DENY
                check(f"{role} GET {path}", r.status_code, expect)
                if expect == DENY:
                    check(f"{role} GET {path} 错误码", r.json()["code"], AUTH_FAIL)

        print("\n=== 管理端：仅管理员 ===")
        admin_paths = (
            "/api/v1/admin/overview",
            "/api/v1/admin/accounts",
            "/api/v1/admin/rule-words",
            "/api/v1/admin/script-lines",
            "/api/v1/admin/ai-logs",
        )
        for role in ("guest", "student", "teacher", "admin"):
            for path in admin_paths:
                r = c.get(path, headers=H(role))
                expect = OK if role == "admin" else DENY
                check(f"{role} GET {path}", r.status_code, expect)

        print("\n=== 未认证访问 ===")
        for path in ("/api/v1/teacher/learners", "/api/v1/admin/overview", "/api/v1/sessions"):
            r = c.get(path)
            check(f"匿名 GET {path}", r.status_code, 401)

        print("\n=== 词表维护：危机组禁止禁用 ===")
        r = c.delete("/api/v1/admin/rule-words/crisis/不想活", headers=H("admin"))
        check("admin 禁用危机词（应拒）", r.status_code, DENY)
        check("admin 禁用危机词 错误码", r.json()["code"], AUTH_FAIL)

        print("\n=== 越权访问他人会话 ===")
        r = c.post("/api/v1/sessions", headers=H("student"), json={"scenario_id": "W-01"})
        sid = r.json()["data"]["id"]
        r = c.get(f"/api/v1/sessions/{sid}", headers=H("teacher"))
        check("teacher 读他人会话（非名下）", r.status_code, DENY)
        r = c.get(f"/api/v1/sessions/{sid}", headers=H("student"))
        check("student 读本人会话", r.status_code, OK)

        print("\n=== 账号停用后立即失效 ===")
        r = c.get("/api/v1/admin/accounts", headers=H("admin"), params={"keyword": "audit_stu"})
        uid = r.json()["data"]["items"][0]["id"]
        c.patch(f"/api/v1/admin/accounts/{uid}/active", headers=H("admin"), json={"active": False})
        r = c.post("/api/v1/auth/login", json={"username": ACCOUNTS["student"], "password": PASSWORD})
        check("停用后登录被拒", r.status_code, 403)
        c.patch(f"/api/v1/admin/accounts/{uid}/active", headers=H("admin"), json={"active": True})
        r = c.post("/api/v1/auth/login", json={"username": ACCOUNTS["student"], "password": PASSWORD})
        check("恢复后登录成功", r.status_code, OK)

    print()
    if FAILURES:
        print(f"❌ {len(FAILURES)} 项不符合预期：")
        for item in FAILURES:
            print("   -", item)
        return 1
    print("✅ 权限矩阵全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())

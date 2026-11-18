"""创建四个角色的演示账号，并把学员挂到教师名下。

用法（服务已启动时可忽略 DB 直连）：
    work\\pyenv\\Scripts\\python.exe work\\seed_demo_accounts.py

账号与密码固定，便于演示与答辩现场直接登录：

| 角色   | 用户名      | 密码           | 能做什么                         |
|--------|-------------|----------------|----------------------------------|
| 学生   | student01   | Student@12345  | 训练、评分、复盘、成长中心       |
| 教师   | teacher01   | Teacher@12345  | 看名下学员、班级看板、学员记录   |
| 管理员 | admin01     | Admin@12345    | 账号/内容/词表/台词/运行状态全权 |
| 访客   | （前端一键） | 无             | 只读浏览案例与知识库             |
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "deliverables" / "backend"
sys.path.insert(0, str(BACKEND))
import os

os.chdir(BACKEND)

from app.core.config import get_settings  # noqa: E402
from app.domain.enums import Role  # noqa: E402
from app.domain.models import Account  # noqa: E402
from app.infra.db import Database  # noqa: E402
from app.services.account_service import create_account  # noqa: E402

DEMO = [
    ("student01", "Student@12345", "学员小李", Role.STUDENT),
    ("student02", "Student@12345", "学员小王", Role.STUDENT),
    ("teacher01", "Teacher@12345", "张老师", Role.TEACHER),
    ("admin01", "Admin@12345", "教务管理员", Role.ADMIN),
]


async def main() -> int:
    settings = get_settings()
    db = Database(settings)
    await db.connect()
    created = 0
    try:
        async with db.session() as session:
            for username, password, nickname, role in DEMO:
                account = await create_account(
                    session, settings, username=username, password=password,
                    nickname=nickname, role=role,
                )
                created += 1
                print(f"  账号 {username:12s} 角色 {role.value:8s} 昵称 {account.nickname}")

        # 把两个学员挂到张老师名下，教师端才有数据可看
        async with db.session() as session:
            teacher = (
                await session.execute(
                    __import__("sqlalchemy").select(Account).where(Account.username == "teacher01")
                )
            ).scalar_one()
            for name in ("student01", "student02"):
                learner = (
                    await session.execute(
                        __import__("sqlalchemy").select(Account).where(Account.username == name)
                    )
                ).scalar_one()
                learner.teacher_id = teacher.id
            await session.commit()
            print(f"  已把 student01 / student02 挂到 teacher01（{teacher.nickname}）名下")
    finally:
        await db.disconnect()

    print(f"\n共处理 {created} 个账号。登录口令见脚本头部注释。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

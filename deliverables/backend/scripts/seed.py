"""把 12 个案例与 19 张技巧卡写入数据库（幂等）。

用法：
    python scripts/seed.py            # 读取 Settings 里的 DATABASE_URL
    python scripts/seed.py --reset    # 先清空 scenarios/knowledge_cards 再写入
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.domain.models import KnowledgeCard, Scenario  # noqa: E402
from app.infra.db import Database  # noqa: E402
from app.services.content_service import seed_content  # noqa: E402


async def _run(reset: bool) -> None:
    settings = get_settings()
    database = Database(settings)
    await database.connect()
    try:
        async with database.session() as session:
            if reset:
                await session.execute(delete(KnowledgeCard))
                await session.execute(delete(Scenario))
                await session.commit()
            counts = await seed_content(session)
        print(f"seed ok: {counts['scenarios']} scenarios, {counts['knowledge_cards']} cards")
    finally:
        await database.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="写入案例与知识卡种子数据")
    parser.add_argument("--reset", action="store_true", help="先清空再写入")
    args = parser.parse_args()
    asyncio.run(_run(args.reset))


if __name__ == "__main__":
    main()

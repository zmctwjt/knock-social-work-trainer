"""生成演示用训练数据，让教师看板、趋势图、热力图都有内容。

不直接 INSERT 假数据，而是走与生产相同的 service 层（建会话→发言→评分→结案），
保证数据满足外键与状态机约束，统计口径也不会因为"手写假数据"而失真。

用法：
    work\\pyenv\\Scripts\\python.exe work\\seed_training_data.py [每个学员训练次数]
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "deliverables" / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.domain.models import Account, Scenario  # noqa: E402
from app.infra.db import Database  # noqa: E402
from app.infra.cache import AICache  # noqa: E402
from app.infra.redis import create_store  # noqa: E402
from app.services import session_service  # noqa: E402
from app.services.ai_gateway import AIGateway  # noqa: E402
from app.services.audit_service import AuditRecorder  # noqa: E402
from app.services.llm.quota import DailyQuota  # noqa: E402
from app.services.llm.router import ModelRouter  # noqa: E402
from app.services.llm.usage import UsageTracker  # noqa: E402
from app.services.llm.zhipu import ZhipuProvider  # noqa: E402


def build_gateway(settings, db: Database) -> AIGateway:
    """构造真实网关；无 API key 时它内部会降级为规则结果，正好符合演示需要。"""
    store = create_store(settings)
    cache = AICache(store, ttl_sec=settings.glm_cache_ttl_sec, max_size=settings.glm_cache_max)
    quota = DailyQuota(store, daily_cap=settings.glm_daily_cap)
    provider = ZhipuProvider(settings)
    router = ModelRouter(settings, provider)
    audit = AuditRecorder(db.session)
    return AIGateway(settings, router, cache, quota, usage=UsageTracker(), audit=audit)

#: 各阶段可用的学生发言，覆盖高分与低分行为，让六维分数有区分度
UTTERANCES = [
    "王阿姨您好，我是社区的小陈，今天想陪您聊聊最近的情况，您方便吗？",
    "听起来这段时间您一个人扛了很多，能跟我说说最难受的是什么时候吗？",
    "您一个人吃饭，做多了吃不完，这种日子确实不好受。",
    "我能理解您现在的心情，换作是我也会有同样的感受。",
    "您愿意跟我多讲讲，最近睡眠不好的时候都在想些什么吗？",
    "如果方便的话，我们可以一起想想有没有能让您轻松一点的办法。",
    "您刚才说的这些，我记下来了，我们慢慢来。",
    "您现在最希望有人帮您做的是什么？",
]


async def main() -> int:
    per_learner = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    settings = get_settings()
    db = Database(settings)
    await db.connect()
    gateway = build_gateway(settings, db)
    made = 0
    try:
        async with db.session() as session:
            learners = list(
                (await session.execute(
                    select(Account).where(Account.role == "student", Account.is_guest.is_(False))
                )).scalars()
            )
            scenarios = list(
                (await session.execute(select(Scenario).where(Scenario.active.is_(True)))).scalars()
            )
            if not learners or not scenarios:
                print("缺少学生账号或案例，请先运行 seed 脚本")
                return 1
            teacher = (
                await session.execute(select(Account).where(Account.role == "teacher"))
            ).scalars().first()

            random.seed(20261118)  # 固定种子，重复运行得到相似分布
            for learner in learners:
                for i in range(per_learner):
                    sc = random.choice(scenarios)
                    created = await session_service.create_session(
                        session,
                        learner,
                        scenario_id=sc.id,
                        difficulty=None,
                        blindfold=False,
                        max_turns=40,
                        client_session_id=f"seed-{learner.id.hex[:6]}-{i}",
                    )
                    sid = created.id
                    for text in random.sample(UTTERANCES, k=random.randint(3, 5)):
                        try:
                            await session_service.submit_turn(
                                session, learner, sid, text=text, gateway=gateway,
                            )
                        except Exception:  # noqa: BLE001 —— 单轮失败不影响整批
                            continue
                    for stage in (1, 2, 3):
                        try:
                            await session_service.score_stage(
                                session, learner, sid, stage_index=stage, gateway=gateway,
                            )
                        except Exception:  # noqa: BLE001
                            continue
                    try:
                        await session_service.finish_session(session, learner, sid)
                    except Exception:  # noqa: BLE001
                        continue
                    made += 1
                if teacher:
                    learner.teacher_id = teacher.id
            await session.commit()
    finally:
        await db.disconnect()

    print(f"已生成 {made} 次完整训练（{len(learners) if 'learners' in dir() else '?'} 名学员）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
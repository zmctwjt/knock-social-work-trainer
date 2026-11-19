"""内容层：案例库与技巧卡（数据库种子 + 读取）。

12 个案例与 19 张技巧卡来自原前端 `src/data/{scenarios,personas,knowledge}.ts`。
迁移到后端后内容成为"服务端数据"：前端不再内置角色卡，改由 `GET /api/v1/scenarios`
下发。这样调整角色台词或补一张技巧卡不需要重新发版，也不会有两份副本互相漂移。

种子写入是幂等的：按主键查重，只补缺失行，不覆盖运营改动过的字段。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.models import Account, KnowledgeCard, Scenario

# ═══════════════════════════════════════════════════════════
# 一、12 个案例（角色卡）
# ═══════════════════════════════════════════════════════════

# 所有角色共用的"出戏检测"词：命中即视为模型脱离角色
COMMON_FORBIDDEN = [
    "作为AI",
    "作为人工智能",
    "我是一个语言模型",
    "我可以帮你",
    "根据你的描述",
    "建议你",
]


def _system_prompt(
    *,
    name: str,
    age: int,
    gender: str,
    archetype: str,
    brief: str,
    emotion: int,
    resistance: int,
) -> str:
    return (
        f"你正在扮演一位社区个案服务对象：{name}，{age} 岁，{gender}，身份是{archetype}。\n"
        f"背景：{brief}\n"
        "你正在接受一名社工实习生的面谈训练。请始终以第一人称、口语化短句回应，"
        "每次只说 1 到 2 句；不主动给建议，不总结对方观点，不跳出角色，不承认自己是 AI。\n"
        f"当前情绪值 {emotion}/100。情绪低时更沉默、回避，情绪高时更愿意多说一点。\n"
        f"阻抗 {resistance}/5。阻抗越高越容易敷衍、反问或转移话题。"
    )


def _scenario(
    scenario_id: str,
    name: str,
    age: int,
    gender: str,
    archetype: str,
    resistance: int,
    difficulty: int,
    sensitive_tag: str | None,
    brief: str,
    emotion: int,
    voice: tuple[str, str, str],
) -> dict:
    return {
        "id": scenario_id,
        "name": name,
        "age": age,
        "gender": gender,
        "archetype": archetype,
        "resistance": resistance,
        "difficulty": difficulty,
        "sensitive_tag": sensitive_tag,
        "brief": brief,
        "initial_emotion": emotion,
        "system_prompt": _system_prompt(
            name=name,
            age=age,
            gender=gender,
            archetype=archetype,
            brief=brief,
            emotion=emotion,
            resistance=resistance,
        ),
        "voice_low": voice[0],
        "voice_mid": voice[1],
        "voice_high": voice[2],
        "forbidden": COMMON_FORBIDDEN,
        "active": True,
    }


SEED_SCENARIOS: list[dict] = [
    _scenario(
        "W-01", "王阿姨", 68, "女", "独居空巢老人", 2, 2, None,
        "老伴去世三年，子女在外地。最近常忘事，怕给儿女添麻烦，嘴上说“我挺好”。",
        45,
        ("说话很轻，常停顿，反复说“没事”", "愿意聊家常，会主动提起老伴", "话多起来，边说边叹气"),
    ),
    _scenario(
        "L-02", "李女士", 35, "女", "单亲母亲", 3, 3, None,
        "独自抚养小学儿子，打两份工。孩子最近成绩下滑，她被老师约谈后情绪崩溃。",
        50,
        ("疲惫、防备，回答很短", "谈起孩子会放松一点", "边哭边说对不起孩子"),
    ),
    _scenario(
        "C-03", "小陈", 15, "男", "厌学青少年", 4, 4, None,
        "初二休学在家，昼夜颠倒打游戏。父母一开口就吵，他说“学校没意思”。",
        30,
        ("低头玩手机，只回“嗯”“不知道”", "聊游戏时话变多", "抱怨父母和老师，语速变快"),
    ),
    _scenario(
        "Z-04", "赵先生", 42, "男", "肢体残障人士", 4, 4, None,
        "工伤致残两年，赔偿未谈拢，觉得自己成了家里负担，不愿出门。",
        35,
        ("回避目光，句子很短", "愿意谈工伤经过", "情绪激动，反复说“没人管我们”"),
    ),
    _scenario(
        "U-05", "刘哥", 48, "男", "失业中年", 3, 3, None,
        "工厂关停后失业半年，瞒着家里每天假装上班，最近开始失眠。",
        40,
        ("坐立不安，说话绕圈子", "谈到以前的工作很自豪", "声音发颤，说“撑不住了”"),
    ),
    _scenario(
        "A-06", "阿珍", 30, "女", "家暴受暴者", 5, 5, "家暴",
        "丈夫酒后多次动手，她带着孩子回娘家住，既怕报复又怕被劝“为了孩子忍忍”。",
        35,
        ("极度警惕，先问“你会告诉我老公吗”", "确认安全后愿意说细节", "哭泣，反复问“我是不是做错了”"),
    ),
    _scenario(
        "G-07", "王奶奶", 81, "女", "失能老人家庭照护者", 3, 3, None,
        "照顾卧床老伴五年，自己也有关节病。女儿劝她送养老院，她舍不得。",
        40,
        ("反应慢，常重复同一句话", "愿意说老伴年轻时的事", "边说边抹眼泪，说“我不放心”"),
    ),
    _scenario(
        "M-08", "马同学", 19, "女", "青少年网络成瘾", 4, 4, None,
        "大一新生，入学后沉迷短视频和直播打赏，挂科两门，开始借网贷。",
        35,
        ("敷衍，先说“我没事”", "聊起直播会兴奋", "承认欠钱后慌乱、求助"),
    ),
    _scenario(
        "B-09", "老周", 62, "男", "社区矫正对象", 5, 5, "社区矫正",
        "因经济纠纷被判缓刑，邻居议论让他抬不起头，拒绝参加社区活动。",
        30,
        ("抵触，反问“你们是不是来监视我的”", "聊到家人会软下来", "情绪爆发，说自己也是受害者"),
    ),
    _scenario(
        "F-10", "林女士", 29, "女", "外来务工新居民", 3, 3, None,
        "随丈夫来本地三年，孩子上学要办居住证，材料跑了四次没办成。",
        45,
        ("拘谨，普通话不流利", "说起孩子上学很着急", "抱怨政策，越说越急"),
    ),
    _scenario(
        "S-11", "老陈", 55, "男", "退役军人", 4, 4, None,
        "退役后安置工作不顺，腰椎旧伤复发，觉得“没人记得我们这些人”。",
        40,
        ("腰板挺直但话少，语气硬", "愿意谈部队经历", "激动，说“当年不是这样的”"),
    ),
    _scenario(
        "H-12", "小雨", 22, "女", "在校心理求助者", 2, 2, "自杀风险",
        "大四毕业压力大，与室友关系紧张，说了“活着没意思”，辅导员转介而来。",
        48,
        ("低头，声音很小，回答“还好”", "愿意谈学业压力", "主动倾诉，情绪起伏明显"),
    ),
]

# ═══════════════════════════════════════════════════════════
# 二、19 张技巧卡
# ═══════════════════════════════════════════════════════════


def _card(card_id: str, title: str, category: str, summary: str, content: str, tags: list[str], stage: int | None) -> dict:
    return {
        "id": card_id,
        "title": title,
        "category": category,
        "summary": summary,
        "content": content,
        "tags": tags,
        "stage": stage,
        "order_index": int(card_id.split("-")[1]),
    }


SEED_KNOWLEDGE_CARDS: list[dict] = [
    _card("T-01", "共情三层次", "共情", "从复述事实到回应感受，再到说出对方没说出口的需要。",
          "第一层是复述事实，第二层是点出情绪，第三层是回应需要。只做第一层像录音机，"
          "直接跳到第三层像算命；先跟着对方走，再往前半步。", ["共情", "倾听"], 1),
    _card("T-02", "毒性正能量陷阱", "共情", "“想开点”“会好的”这类安慰会让人更孤独。",
          "当对方在讲痛苦时，急着给希望等于否定他的感受。先承认“这确实很难”，"
          "再谈资源；情绪没被接住之前，任何建议都会被听成敷衍。", ["共情", "常见错误"], 1),
    _card("T-03", "开放式提问八句式", "提问", "用“什么、怎样、能不能多说一点”代替“是不是、有没有”。",
          "典型句式：能多说一点吗；那时候你是什么感觉；你最担心的是什么；"
          "如果有一点点变化，会是什么样。开放句给对方叙述空间，封闭句只换来是或否。", ["提问", "技术"], 2),
    _card("T-04", "连环问的代价", "提问", "连续三个问题以上，面谈会变成审讯。",
          "每问一个问题，对方都要判断“他想听什么”。提问后先停一停，"
          "等回应里出现情绪词，再顺着情绪问下一句，而不是顺着自己的提纲问。", ["提问", "常见错误"], 2),
    _card("T-05", "沉默的力量", "过程", "沉默不是冷场，是把说话的空间还给对方。",
          "对方哭或长时间不说话时，先别急着填满。数到五，再轻声说一句"
          "“我在这儿，不着急”。沉默陪伴本身就能降低防御。", ["过程", "沉默"], 1),
    _card("T-06", "最小鼓励", "共情", "用“嗯”“然后呢”“我在听”维持对话，不抢话。",
          "最小鼓励是面谈的润滑剂：短、轻、不评价。它让对方知道你在听，"
          "又不会把话题拽到自己身上。", ["共情", "技术"], 1),
    _card("T-07", "复述与澄清", "共情", "把你的理解说出来，请对方修正。",
          "句式：“我听到的是……对吗？”复述的是内容和情绪，不是评价。"
          "对方说“不是”，不是否定你，而是帮你说得更准。", ["共情", "技术"], 2),
    _card("T-08", "从抱怨里找需求", "过程", "抱怨往往指向一个没被满足的需要。",
          "“医院太远了”背后可能是“我怕自己跑不动”。把抱怨翻译成需要，"
          "再问“那对你来说，最要紧的是哪一件”，面谈就从情绪走到行动。", ["过程", "评估"], 2),
    _card("T-09", "总结确认", "过程", "阶段性收束，防止谈了很久却没抓到重点。",
          "每个阶段结束前，用两三句总结“我们今天谈了什么、你决定做什么、我负责跟进什么”，"
          "并请对方确认。总结是给服务对象掌控感，不是给社工做汇报。", ["过程", "技术"], 3),
    _card("T-10", "避免同盟陷阱", "伦理", "站队会让专业关系变成私人关系。",
          "“你家人太过分了”这类附和很解气，但会让对方失去自己解决问题的位置。"
          "中立不等于冷漠，而是把评判换成好奇：发生了什么，你怎么看。", ["伦理", "边界"], 2),
    _card("T-11", "一次只处理一个问题", "过程", "问题清单越长，行动越难开始。",
          "评估出五个问题很正常，但一次面谈只聚焦一个可行动的点。"
          "其他的记下来，明确告诉对方“下次我们谈这个”，避免失焦。", ["过程", "计划"], 3),
    _card("T-12", "面谈五阶段", "过程", "接案、预估、计划、介入、评估结案。",
          "训练舱把一次完整面谈压成三段：建立关系与收集信息、聚焦问题与共同计划、"
          "总结与下一步。阶段之间有明确的转场句，不是聊到哪算哪。", ["过程", "框架"], None),
    _card("T-13", "结束的技巧", "过程", "结束不是戛然而止，要提前预告并收束。",
          "提前三分钟说“我们还有几分钟”，再总结、再确认下一步。"
          "突然结束会让对方觉得被抛弃，尤其在刚刚说出重要事情之后。", ["过程", "技术"], 3),
    _card("T-14", "阻抗不是不配合", "伦理", "抗拒往往是在保护自己。",
          "迟到、沉默、反问、说“你不懂”，都是在说“我还不安全”。"
          "不拆穿、不施压，先把阻抗说出来：“我感觉你不太想谈这个”，反而能松动。", ["伦理", "阻抗"], 2),
    _card("T-15", "提问要留白", "提问", "问题后面留三秒，答案才会出来。",
          "新手最常犯的错是自问自答、问完立刻补一句解释。留白给了对方组织语言的时间，"
          "也传递了“我愿意等你说完”。", ["提问", "节奏"], 1),
    _card("T-16", "三级风险分级", "风险", "无风险、有念头、有计划和手段，处置方式完全不同。",
          "出现“活着没意思”要按高风险对待：当场评估念头、计划、手段、时间，"
          "不承诺保密，立即启动危机处置与转介，并留下可联系的人。", ["风险", "危机"], 2),
    _card("T-17", "给建议 vs 下命令", "建议", "建议要留给对方选择权。",
          "“你必须去申请低保”是命令；“有几个办法，你看看哪个可行”是建议。"
          "建议之前先问“你试过什么、管用吗”，否则容易否定了对方的努力。", ["建议", "技术"], 2),
    _card("T-18", "对质的时机", "伦理", "对质是为了澄清，不是为了赢。",
          "当对方说法前后矛盾且影响安全时才对质，句式是“我注意到你前面说 A，"
          "刚才说 B，我有点没跟上”，而不是“你在撒谎”。", ["伦理", "对质"], 3),
    _card("T-19", "转介四步", "风险", "说明理由、征得同意、陪同对接、回访确认。",
          "转介不是甩包袱：先讲清为什么需要别的专业力量，再征得同意，"
          "把联系方式与流程交到对方手上，最后回访确认真的接上了。", ["风险", "转介"], 3),
]

# ═══════════════════════════════════════════════════════════
# 三、读写
# ═══════════════════════════════════════════════════════════


async def seed_content(session: AsyncSession) -> dict[str, int]:
    """幂等补齐案例与技巧卡，返回本次新增条数。"""
    created = {"scenarios": 0, "knowledge_cards": 0}

    existing_scenarios = set(
        (await session.execute(select(Scenario.id))).scalars().all()
    )
    for row in SEED_SCENARIOS:
        if row["id"] in existing_scenarios:
            continue
        session.add(Scenario(**row))
        created["scenarios"] += 1

    existing_cards = set(
        (await session.execute(select(KnowledgeCard.id))).scalars().all()
    )
    for row in SEED_KNOWLEDGE_CARDS:
        if row["id"] in existing_cards:
            continue
        session.add(KnowledgeCard(**row))
        created["knowledge_cards"] += 1

    await session.commit()
    return created


async def list_scenarios(session: AsyncSession, *, include_inactive: bool = False) -> list[Scenario]:
    stmt = select(Scenario).order_by(Scenario.id)
    if not include_inactive:
        stmt = stmt.where(Scenario.active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def get_scenario(session: AsyncSession, scenario_id: str) -> Scenario:
    scenario = await session.get(Scenario, scenario_id)
    if scenario is None or not scenario.active:
        raise AppError.not_found(f"案例 {scenario_id} 不存在或已下线")
    return scenario


async def list_cards(
    session: AsyncSession,
    *,
    category: str | None = None,
    keyword: str | None = None,
) -> list[KnowledgeCard]:
    """技巧卡列表。`keyword` 在标题、摘要、正文与标签里做包含匹配。

    任务书要求知识库"支持按案例与关键词检索"；这里不引入全文索引，
    数据量级（19 张卡 + 伦理条目）下 `LIKE` 足够，且不依赖 MySQL 版本特性。
    """
    stmt = select(KnowledgeCard).order_by(KnowledgeCard.order_index)
    if category:
        stmt = stmt.where(KnowledgeCard.category == category)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            KnowledgeCard.title.like(like)
            | KnowledgeCard.summary.like(like)
            | KnowledgeCard.content.like(like)
        )
    return list((await session.execute(stmt)).scalars().all())


async def scenario_owner_names(
    session: AsyncSession, rows: list[Scenario]
) -> dict[uuid.UUID, str]:
    """批量取创建者昵称，避免列表接口 N+1 查询。"""
    ids = {r.created_by for r in rows if r.created_by}
    if not ids:
        return {}
    result = await session.execute(
        select(Account.id, Account.nickname).where(Account.id.in_(ids))
    )
    return {row[0]: row[1] for row in result.all()}

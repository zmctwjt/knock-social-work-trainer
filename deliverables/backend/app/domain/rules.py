"""本地关键词规则引擎（由 `src/services/rules.ts` 1:1 移植）。

四条不可动摇的实现纪律：
1. 敬称归一化必须在匹配之前完成，否则「您应该」永远命中不了「你应该」；
2. 规则命中即免调 AI（控秒点的核心）；
3. 危机级内容永不进入模型，由本地硬规则拦截；
4. 词表只维护「你」版本，归一化负责覆盖敬称。

判定顺序即优先级，不可调整：危机 → 评判 → 建议过早 → 离题 →
沉默陪伴 → 共情 → 开放式提问 → 封闭式提问（特征式）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import DimensionKey, Intent, RiskLevel

# ═══════════════════════════════════════════════════════════
# 一、归一化与工具
# ═══════════════════════════════════════════════════════════


def normalize(text: str) -> str:
    """生成用于匹配的归一化文本；绝不回写学生原文。

    顺序敏感：长模式必须先于短模式，否则「您自己」会先被「您」替换。
    """
    return (
        text.replace("您们方", "我们方")
        .replace("您们", "你们")
        .replace("您自己", "你自己")
        .replace("您", "你")
        .replace("咱们", "我们")
        .replace("咱", "我们")
    )


#: 去空白与标点使用的字符集（与 rules.ts 的 stripPunctuation 等价）
_PUNCTUATION = set(
    " \t\r\n\u3000，。！？、；：“”‘’（）【】,.!?;:'\"()[]<>《》—…·"
)


def strip_punctuation(text: str) -> str:
    return "".join(ch for ch in text if ch not in _PUNCTUATION)


def find_hits(text: str, words: list[str] | tuple[str, ...]) -> list[str]:
    return [w for w in words if w and w in text]


# ═══════════════════════════════════════════════════════════
# 二、词表（9 张，共 162 条）
# ═══════════════════════════════════════════════════════════

EMPATHY_WORDS: list[str] = [
    "我理解", "我能理解", "我能感受到", "听起来你", "感觉你",
    "我理解你现在", "你一个人撑着", "你这些年不容易", "你已经撑了很久",
    "辛苦你了", "这确实很难", "换了我也会", "这让人很难受",
    "你有这样的感觉是正常的", "会这么想很正常", "这确实不是你的错",
]

OPEN_QUESTION_WORDS: list[str] = [
    "什么", "什么时候", "怎么样", "怎么想", "怎么看",
    "怎么", "如何", "后来呢", "然后呢", "能说说",
    "多说说", "聊聊", "讲讲", "展开说说", "举个例子",
    "那段时间", "当时", "具体是", "后来发生", "从什么时候开始",
    "你说的这个", "能具体说说",
]

CLOSED_QUESTION_SUFFIX: list[str] = ["吗", "吧", "对吧", "是不是", "有没有", "好不好"]

#: 评判词表。不要收录「你怎么」：它是「你怎么看/怎么想」的公共前缀。
JUDGE_WORDS: list[str] = [
    "你应该", "你必须", "你不该", "你怎么能", "你怎么回事", "你这个人",
    "你这样不行", "你太天真了", "你听我的没错", "你这是错的", "这样不对",
    "你太过分了", "都是你的问题", "你这是逃避", "你就是不想面对",
    "这有什么", "这算什么", "想开点", "别想太多", "多大点事",
    "不至于", "你也太矫情了", "孝顺", "不孝", "女人就该", "男人都这样",
    "一个巴掌拍不响", "你自己也有责任", "你就是想太多", "有什么好难过的",
]

PREMATURE_ADVICE_WORDS: list[str] = [
    "你应该去", "你最好去", "我建议你", "你要不要考虑", "你必须面对",
    "你不用管了", "没什么大不了", "你要坚强", "忍一忍就过去了",
    "建议你去", "劝你", "你应该早点", "你最好马上", "你先别问了",
    "你就应该", "听我的没错", "我比你懂",
]

SILENCE_ACCOMPANY_WORDS: list[str] = [
    "我在这儿听着", "我在这里", "不着急", "慢慢说", "想好了再说",
    "不说话也可以", "没关系", "你先歇会儿", "什么时候想说了就说",
]

OFF_TOPIC_WORDS: list[str] = [
    "我先去上个厕所", "我要去洗手间", "今天星期几", "现在几点了",
    "外面下雨了吗", "你几岁", "你叫什么名字", "你今年多大",
    "你是真人吗", "你是不是机器人", "帮我查一下", "换个话题",
    "我不想聊了", "我饿了", "帮我倒杯水", "你有微信吗",
]

#: 危机级词表：命中即本地硬拦截，绝不调用模型。
#: 「活着没意思」「没盼头」不在此表 —— 属于无望感（关注级）。
CRISIS_WORDS: list[str] = [
    "自杀", "想死", "不想活", "死了算了", "活不下去", "结束生命",
    "了结自己", "一了百了", "活着没意义不如死", "不如死了",
    "割腕", "割手", "跳楼", "跳河", "上吊", "吞药",
    "吃药自杀", "划伤自己", "伤害自己",
    "打死我", "要杀我", "掐我脖子", "他打我", "拿刀",
    "把我推下去", "打我",
    "我不配活着", "反正也没人在乎我死活", "死了更好",
]

#: 「打我」类词的致电语境左邻词：「你可以打我电话」不是被害陈述。
_DIALING_LEFT = ["可以", "可", "能", "给", "帮", "替", "让", "请", "麻烦", "打", "用"]
_DIALING_RIGHT = ["电话", "手机", "号码", "手机号", "微信", "座机"]

#: 「拿刀」类词的烹饪语境右邻字：「拿刀切菜」不是威胁。
_CUTTING_RIGHT = ("切", "剁", "削")

#: 无望感词表（关注级）。不收录「随便/都行/无所谓/习惯了/没用」等中性高频词。
HOPELESSNESS_WORDS: list[str] = [
    "活着没意思", "没意思", "没盼头", "没指望", "看不到头", "看不到希望",
    "没劲", "没希望", "我这种人", "我这老太婆", "拖累", "活够了",
    "就这样过呗", "反正也一样", "熬日子", "等死", "白活了",
]

#: 毒性正能量：对无望感说「别想太多」会把临床线索关掉。
TOXIC_POSITIVITY_WORDS: list[str] = [
    "别想太多", "想开点", "你要乐观", "开心点", "别难过", "没什么大不了",
    "你要坚强", "看开些", "会好起来的",
]

#: 空泛共情检测用的具体内容标记。
CONCRETE_MARKERS: list[str] = [
    "时候", "那天", "心里", "难受", "辛苦", "不容易", "一个人",
    "撑着", "熬", "怕", "担心", "难", "累", "孤独", "寂寞", "空",
]


# ═══════════════════════════════════════════════════════════
# 三、危机词边界感知匹配
# ═══════════════════════════════════════════════════════════


def find_crisis_hits(raw_input: str) -> list[str]:
    """危机词匹配，带致电/烹饪语境豁免。

    为什么不能用裸 `includes`：「你可以打我电话」含「打我」会被误判
    suicidal；「拿刀切菜」含「拿刀」同样误伤。判定权在上下文，不在子串。
    """
    text = normalize(raw_input)
    out: list[str] = []
    for word in CRISIS_WORDS:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx < 0:
                break
            left = text[:idx]
            right = text[idx + len(word):]
            dialing = "打我" in word and (
                any(right.startswith(r) for r in _DIALING_RIGHT)
                or any(left.endswith(item) for item in _DIALING_LEFT)
            )
            cutting = "刀" in word and right.startswith(_CUTTING_RIGHT)
            if not dialing and not cutting:
                out.append(word)
                break
            start = idx + 1
    return out


# ═══════════════════════════════════════════════════════════
# 四、判定结果与评分动作表
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RuleEffects:
    emotion_delta: int = 0
    score_deltas: dict[DimensionKey, int] = field(default_factory=dict)
    note: str = ""
    source: str = ""


@dataclass(frozen=True)
class MatchResult:
    intent: Intent
    risk_level: RiskLevel
    hit_words: list[str]
    effects: RuleEffects
    should_call_ai: bool


NO_EFFECT = RuleEffects()

#: 八类意图的标准评分动作（规则层与 AI 补判共用同一张表，杜绝两套账）。
INTENT_EFFECTS: dict[Intent, RuleEffects] = {
    Intent.EMPATHY: RuleEffects(
        emotion_delta=8,
        score_deltas={DimensionKey.EMPATHY: 8},
        note="准确接住并传达了服务对象的感受",
        source="公告第 426 号 · 6.1.1 同感",
    ),
    Intent.OPEN_QUESTION: RuleEffects(
        emotion_delta=5,
        score_deltas={DimensionKey.QUESTION: 8},
        note="开放式提问有助于展开话题",
        source="公告第 426 号 · 6.1.2 提问",
    ),
    Intent.CLOSED_QUESTION: RuleEffects(
        emotion_delta=-3,
        score_deltas={DimensionKey.QUESTION: -3},
        note="封闭式提问压缩了对方的表达空间",
        source="公告第 426 号 · 6.1.2 提问",
    ),
    Intent.JUDGEMENT: RuleEffects(
        emotion_delta=-8,
        score_deltas={DimensionKey.ETHICS: -8},
        note="命中「说教训导」或评判表达，违反非评判原则",
        source="公告第 426 号 · 4.2.5 非评判原则",
    ),
    Intent.PREMATURE_ADVICE: RuleEffects(
        emotion_delta=-5,
        score_deltas={DimensionKey.ADVICE: -8},
        note="在尚未充分了解情况时给出方案，违反「对情况和需要了解评估后」的要求",
        source="公告第 426 号 · 6.1.3 影响性技巧",
    ),
    Intent.SILENCE: RuleEffects(
        emotion_delta=6,
        score_deltas={DimensionKey.EMPATHY: 6},
        note="服务对象沉默时给出空间，符合「专注」技巧",
        source="公告第 426 号 · 6.1.1 专注",
    ),
    Intent.OFF_TOPIC: RuleEffects(
        emotion_delta=-5,
        score_deltas={},
        note="未接住服务对象当前的话，六维分数不变",
        source="",
    ),
    Intent.CRISIS: RuleEffects(
        emotion_delta=-10,
        score_deltas={DimensionKey.ETHICS: -12},
        note="命中危机词，由本地硬规则拦截，不调用模型",
        source="公告第 426 号 · 6.8.3",
    ),
}


def _copy_effects(effects: RuleEffects) -> RuleEffects:
    return RuleEffects(
        emotion_delta=effects.emotion_delta,
        score_deltas=dict(effects.score_deltas),
        note=effects.note,
        source=effects.source,
    )


def effects_for_intent(intent: Intent) -> RuleEffects:
    """按意图取标准评分动作（AI 补判覆盖 intent 后重新计分用）。"""
    return _copy_effects(INTENT_EFFECTS.get(intent, NO_EFFECT))


# ═══════════════════════════════════════════════════════════
# 五、辅助判定
# ═══════════════════════════════════════════════════════════


def is_vague_empathy(text: str, empathy_word: str) -> bool:
    """空泛共情：共情词后 15 个字符内没有任何具体内容标记。"""
    idx = text.find(empathy_word)
    if idx < 0:
        return False
    tail = text[idx + len(empathy_word): idx + len(empathy_word) + 15]
    if not tail.strip():
        return True
    return not any(marker in tail for marker in CONCRETE_MARKERS)


def check_hopelessness(text: str) -> RiskLevel:
    """无望感检测（关注级）。危机级判定必须先于本函数完成。"""
    normalized = normalize(text)
    if find_hits(normalized, HOPELESSNESS_WORDS):
        return RiskLevel.HOPELESSNESS
    return RiskLevel.NONE


def is_toxic_positivity(raw_input: str) -> bool:
    return bool(find_hits(normalize(raw_input), TOXIC_POSITIVITY_WORDS))


# ═══════════════════════════════════════════════════════════
# 六、核心判定（顺序即优先级）
# ═══════════════════════════════════════════════════════════


def match_local_rules(raw_input: str) -> MatchResult:
    """本地规则判定。

    `should_call_ai=True` 表示规则库未覆盖，应交给 AI 补判；
    此时 `intent` 只是占位（共情），调用方必须用 AI 结果覆盖，
    并改用 `effects_for_intent(ai_intent)` 的分值口径。
    """
    text = normalize(raw_input)

    # 1. 危机级：最高优先，本地硬拦截
    crisis_hit = find_crisis_hits(text)
    if crisis_hit:
        return MatchResult(
            intent=Intent.CRISIS,
            risk_level=RiskLevel.SUICIDAL,
            hit_words=crisis_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.CRISIS]),
            should_call_ai=False,
        )

    # 2. 评判
    judge_hit = find_hits(text, JUDGE_WORDS)
    if judge_hit:
        return MatchResult(
            intent=Intent.JUDGEMENT,
            risk_level=check_hopelessness(text),
            hit_words=judge_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.JUDGEMENT]),
            should_call_ai=False,
        )

    # 3. 建议过早
    premature_hit = find_hits(text, PREMATURE_ADVICE_WORDS)
    if premature_hit:
        return MatchResult(
            intent=Intent.PREMATURE_ADVICE,
            risk_level=check_hopelessness(text),
            hit_words=premature_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.PREMATURE_ADVICE]),
            should_call_ai=False,
        )

    # 4. 离题：必须排在提问判定之前
    off_topic_hit = find_hits(text, OFF_TOPIC_WORDS)
    if off_topic_hit:
        return MatchResult(
            intent=Intent.OFF_TOPIC,
            risk_level=check_hopelessness(text),
            hit_words=off_topic_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.OFF_TOPIC]),
            should_call_ai=False,
        )

    # 5. 沉默陪伴。这里不能直接判 risk_level=none：
    #    「没关系，活着没意思」是安抚 + 无望感的复合句，风险必须继续透传。
    silence_hit = find_hits(text, SILENCE_ACCOMPANY_WORDS)
    if silence_hit:
        return MatchResult(
            intent=Intent.SILENCE,
            risk_level=check_hopelessness(text),
            hit_words=silence_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.SILENCE]),
            should_call_ai=False,
        )

    # 6. 共情（含空泛共情减半）
    empathy_hit = find_hits(text, EMPATHY_WORDS)
    if empathy_hit:
        vague = is_vague_empathy(text, empathy_hit[0])
        base = INTENT_EFFECTS[Intent.EMPATHY]
        delta = 4 if vague else base.emotion_delta
        return MatchResult(
            intent=Intent.EMPATHY,
            risk_level=check_hopelessness(text),
            hit_words=empathy_hit,
            effects=RuleEffects(
                emotion_delta=delta,
                score_deltas={DimensionKey.EMPATHY: delta},
                note=(
                    "空泛共情，后文未具体化。标准要求「理解准确并将其传达」"
                    if vague
                    else base.note
                ),
                source=base.source,
            ),
            should_call_ai=False,
        )

    # 7. 开放式提问
    open_hit = find_hits(text, OPEN_QUESTION_WORDS)
    if open_hit:
        return MatchResult(
            intent=Intent.OPEN_QUESTION,
            risk_level=check_hopelessness(text),
            hit_words=open_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.OPEN_QUESTION]),
            should_call_ai=False,
        )

    # 8. 封闭式提问（特征式）
    closed_hit = find_hits(text, CLOSED_QUESTION_SUFFIX)
    if closed_hit:
        return MatchResult(
            intent=Intent.CLOSED_QUESTION,
            risk_level=check_hopelessness(text),
            hit_words=closed_hit,
            effects=_copy_effects(INTENT_EFFECTS[Intent.CLOSED_QUESTION]),
            should_call_ai=False,
        )

    # 9. 空输入视为沉默陪伴
    if not text.strip():
        base = INTENT_EFFECTS[Intent.SILENCE]
        return MatchResult(
            intent=Intent.SILENCE,
            risk_level=RiskLevel.NONE,
            hit_words=[],
            effects=RuleEffects(
                emotion_delta=base.emotion_delta,
                score_deltas=dict(base.score_deltas),
                note="本轮未发言，给予沉默空间",
                source=base.source,
            ),
            should_call_ai=False,
        )

    # 10. 规则库未覆盖 —— 只有走到这里才允许调用 AI 分类。
    #     故意给空分值：规则层没看懂这句话，就不该凭占位意图加分。
    return MatchResult(
        intent=Intent.EMPATHY,
        risk_level=check_hopelessness(text),
        hit_words=[],
        effects=RuleEffects(
            note="这句话未命中本地规则库，已交由语义层判定",
            source="规则未覆盖 · 由 AI 补判",
        ),
        should_call_ai=True,
    )


# ═══════════════════════════════════════════════════════════
# 七、词表统计（关于页与自检用）
# ═══════════════════════════════════════════════════════════

_RULE_TABLES: list[tuple[str, list[str], str]] = [
    ("共情词表", EMPATHY_WORDS, "识别接住情绪的表达，区分具体共情与空泛共情"),
    ("开放式提问词表", OPEN_QUESTION_WORDS, "识别引导展开的提问"),
    ("封闭式提问特征表", CLOSED_QUESTION_SUFFIX, "识别压缩表达空间的是非题"),
    ("评判词黑名单", JUDGE_WORDS, "拦截违反非评判原则的说教表达"),
    ("建议过早词表", PREMATURE_ADVICE_WORDS, "拦截未充分了解就给方案的越界"),
    ("沉默陪伴词表", SILENCE_ACCOMPANY_WORDS, "识别愿意等待、不催促的回应"),
    ("离题词表", OFF_TOPIC_WORDS, "识别未接住对方话题的内容"),
    ("危机级词表", CRISIS_WORDS, "自伤意念硬拦截，永不调用模型"),
    ("无望感词表", HOPELESSNESS_WORDS, "关注级信号，引导探索而非拦截"),
]


def count_rule_words() -> int:
    return sum(len(words) for _name, words, _purpose in _RULE_TABLES)


def describe_rule_tables() -> list[dict[str, object]]:
    return [
        {"name": name, "count": len(words), "purpose": purpose}
        for name, words, purpose in _RULE_TABLES
    ]

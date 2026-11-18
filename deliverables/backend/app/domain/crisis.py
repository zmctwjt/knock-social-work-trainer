"""三级风险分级与危机处置（由 `src/services/crisis.ts` 移植）。

核心区分：
  无         —— 无风险线索
  关注级     —— 无望感表达（「活着没意思」「没盼头」），需引导探索，不拦截
  危机级     —— 自伤意念（「不想活」「自杀」），本地硬拦截，永不调用模型

之所以这么分：社工专业要求把无望感表达当作「可探索的临床线索」，
而不是需要立刻堵住的危险。对无望感说「别这么想、您要乐观」属于
「毒性正能量」，会把信号关掉，比不回应更糟。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import RiskLevel
from app.domain.rules import (
    HOPELESSNESS_WORDS,
    find_crisis_hits,
    is_toxic_positivity,
    normalize,
)


def classify_risk(raw_input: str) -> RiskLevel:
    """三级风险判定。危机级必须先于无望感判定。"""
    text = normalize(raw_input)
    if find_crisis_hits(text):
        return RiskLevel.SUICIDAL
    if any(word in text for word in HOPELESSNESS_WORDS):
        return RiskLevel.HOPELESSNESS
    return RiskLevel.NONE


# ═══════════════════════════════════════════════════════════
# 一、关注级：无望感表达的处理
# ═══════════════════════════════════════════════════════════


def hopelessness_hint(raw_input: str) -> str | None:
    """无望感表达后的界面提示条文案；非关注级返回 None。"""
    if classify_risk(raw_input) != RiskLevel.HOPELESSNESS:
        return None
    if is_toxic_positivity(raw_input):
        return (
            "注意：这属于「毒性正能量」回应。标准要求「理解准确并将其传达给服务对象」，"
            "而不是用乐观覆盖她的感受。正确动作是往下探索——这种感觉是从什么时候开始的？"
        )
    return (
        "这是无望感表达，按三级风险分级属关注级，不触发危机拦截。"
        "建议往下探索具体感受，不要急于安抚或转移话题。"
    )


def recommended_direction(raw_input: str) -> str:
    if is_toxic_positivity(raw_input):
        return "downward"
    if classify_risk(raw_input) == RiskLevel.HOPELESSNESS:
        return "downward"
    return "neutral"


# ═══════════════════════════════════════════════════════════
# 二、危机级：硬拦截卡片
# ═══════════════════════════════════════════════════════════


@dataclass
class CrisisHotline:
    code: str
    label: str


@dataclass
class CrisisCard:
    level: str = "suicidal"
    title: str = "已暂停本次训练 · 本轮不计分"
    principles: list[str] = field(default_factory=list)
    hotlines: list[CrisisHotline] = field(default_factory=list)
    citation: str = ""
    disclaimer: str = ""


def build_crisis_card(raw_input: str) -> CrisisCard | None:
    """生成《危机干预提示卡》内容；非危机级返回 None。

    合规要求：卡上号码必须真实可用、不得编造；本卡只提供处置指引，
    不做安全评估结论；命中后界面暂停对话输入，本轮不计分。
    """
    if classify_risk(raw_input) != RiskLevel.SUICIDAL:
        return None

    return CrisisCard(
        principles=[
            "如果这是真实情境，请这样做：",
            "1. 不要单独处理，立即联系你的专业督导。",
            "2. 如实记录：时间、对话内容、你的观察。",
            "3. 不要承诺保密——安全例外优先于保密原则。",
            "4. 不离开，保持在场的姿态，等待专业人员介入。",
            "5. 不要独自做安全评估结论。",
        ],
        hotlines=[
            CrisisHotline(
                code="12356",
                label="全国统一心理援助热线 · 24 小时 · 免费 · 精神科医师与心理治疗师接听",
            ),
            CrisisHotline(code="110", label="报警"),
            CrisisHotline(code="120", label="急救"),
        ],
        citation=(
            "依据：国家卫生健康委《关于应用「12356」全国统一心理援助热线电话号码的通知》"
            "（国卫医政函〔2024〕259 号）。"
        ),
        disclaimer=(
            "本作品是沟通训练工具，不做安全评估，也不承担危机处理职能。"
            "校内支持渠道请在使用前自行填写，此处不预置未经核实的号码。"
        ),
    )


# ═══════════════════════════════════════════════════════════
# 三、AI 建议卡（按情绪值与评判次数切换）
# ═══════════════════════════════════════════════════════════


@dataclass
class SuggestionCard:
    title: str
    quote: str
    basis: str


def build_suggestion(
    emotion: int,
    judge_count: int,
    hopeless_detected: bool,
    last_utterance: str = "",
) -> SuggestionCard:
    last = last_utterance.strip()

    # ① 说教/命令口吻 → 立刻纠偏（优先级最高）
    if any(
        token in last
        for token in ("你应该", "你必须", "你不该", "别想太多", "这有什么", "没必要")
    ):
        return SuggestionCard(
            title="建议 · 刚才那句有说教味",
            quote="您是想让我帮您拿个主意，还是先听您说说？",
            basis=(
                "刚才的话里带了「应该 / 必须」，属于替对方做决定（公告第 426 号 · 4.2.5 非评判原则）。"
                "把选择权交回去，比直接给方案更容易让对方开口。"
            ),
        )

    # ② 空泛共情 → 给出具体化示范
    if len(last) <= 6 and any(token in last for token in ("理解", "明白", "懂")):
        return SuggestionCard(
            title="建议 · 共情可以再具体一点",
            quote="您说一个人过日子，最难的是哪一段？",
            basis=(
                "只说「我理解」而不接任何具体内容，会判为空泛共情（该维度不得高于 50 分）。"
                "把对方刚说的处境复述一遍，再问一个具体的点。"
            ),
        )

    # ③ 已经在追问 → 顺着往下走深一层
    if len(last) > 6 and any(token in last for token in ("吗", "呢", "什么", "怎么", "说说")):
        return SuggestionCard(
            title="建议 · 顺着这个点再深一层",
            quote="那时候，您心里是什么感觉？",
            basis=(
                "刚才那句已经是开放式提问，做对了。再往下可以从「事情」走到「感受」，"
                "这是问题探索阶段的核心动作（公告第 426 号 · 6.1.2 引领性技巧）。"
            ),
        )

    # ④ 评判累计 3 次 → 纠偏优先
    if judge_count >= 3:
        return SuggestionCard(
            title="建议 · 出现说教倾向",
            quote="我理解您现在最想让他做点什么。",
            basis=(
                "本阶段已累计 3 次命中评判词表（4.2.5 非评判原则）。"
                "先把决定权交回给对方，再谈做法。"
            ),
        )

    if emotion < 35:
        return SuggestionCard(
            title="建议 · 对抗中，先给空间",
            quote="没关系的，我下周再来。",
            basis=(
                f"情绪值已降至 {emotion}，低于 35。按 T-05「沉默的力量」此刻不要推进话题，"
                "给一个不丢面子的台阶比追问更有效。"
            ),
        )

    if emotion <= 60:
        if hopeless_detected:
            return SuggestionCard(
                title="建议 · 观望中，可以往下问",
                quote="那这种感觉，是从什么时候开始有的？",
                basis=(
                    "服务对象已表达无望感但未正面回答。"
                    "改用「开始有」降低压力，把话题停在对方愿意接的地方。"
                ),
            )
        return SuggestionCard(
            title="建议 · 观望中，先接住再说",
            quote="您刚才说的这些，听着挺沉的。",
            basis=(
                f"当前情绪值 {emotion}，仍在观望区间。按 T-08「从抱怨里找需求」，"
                "先把情绪接住，再往具体的事上收。"
            ),
        )

    return SuggestionCard(
        title="建议 · 开放中，可以深入",
        quote="那时候你一个人，是怎么过来的？",
        basis=(
            f"当前情绪值 {emotion}，服务对象已建立信任。按 T-07「复述与澄清」，"
            "可以从时间线切入，追问那段时间的应对方式。"
        ),
    )

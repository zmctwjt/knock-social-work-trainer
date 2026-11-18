"""六维评分引擎（由 `src/services/scoring.ts` 移植）。

核心公式：综合分 = 规则底分 × 0.4 + AI 评分 × 0.6。
该配比的意义：即使 AI 完全不可用，规则底分仍能给出有专业依据的分数，
因此"AI 缺项时整条降级、只用规则底分"，绝不拼出半张表。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import DIMENSION_ORDER, DimensionKey, Intent, RiskLevel, Speaker
from app.domain.rules import (
    is_toxic_positivity,
    match_local_rules,
    strip_punctuation,
)

# ═══════════════════════════════════════════════════════════
# 一、六维定义（全部锚定国标条款）
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DimensionMeta:
    key: DimensionKey
    name: str
    short: str
    weight: int
    source: str
    criteria: str


DIMENSIONS: tuple[DimensionMeta, ...] = (
    DimensionMeta(
        key=DimensionKey.EMPATHY,
        name="同感与倾听",
        short="同感倾听",
        weight=25,
        source="公告第 426 号 · 6.1.1 支持性技巧",
        criteria=(
            "积极倾听、专注、鼓励、同感。能否准确接住服务对象的情绪并让对方感到被理解。"
            "空泛的共情（例如只说「我理解」而不接任何具体内容）不得高于 50 分。"
        ),
    ),
    DimensionMeta(
        key=DimensionKey.QUESTION,
        name="提问与对焦",
        short="提问对焦",
        weight=20,
        source="公告第 426 号 · 6.1.2 引领性技巧",
        criteria=(
            "提问、澄清、对焦、摘要。能否用开放式提问打开话题，并把散乱的话题收拢到焦点上。"
            "连续使用封闭式提问应扣分。"
        ),
    ),
    DimensionMeta(
        key=DimensionKey.ADVICE,
        name="信息提供与建议",
        short="信息建议",
        weight=15,
        source="公告第 426 号 · 6.1.3 影响性技巧",
        criteria=(
            "信息提供、自我披露、建议、忠告、对质。能否在合适时机给出信息与选项而不越界下命令。"
            "出现「你必须/你应该」直接扣分。"
        ),
    ),
    DimensionMeta(
        key=DimensionKey.ETHICS,
        name="伦理原则",
        short="伦理原则",
        weight=20,
        source="公告第 426 号 · 4.2.4–4.2.7 接纳·非评判·自决·保密",
        criteria=(
            "接纳、非评判、自决、保密。是否做到不评价不指责、不替服务对象做决定、不泄露信息。"
            "只要出现评判或说教，本维度不得高于 60 分。"
        ),
    ),
    DimensionMeta(
        key=DimensionKey.PROCESS,
        name="过程完整性",
        short="过程完整",
        weight=10,
        source="公告第 426 号 · 6.1 个案服务过程",
        criteria=(
            "接案、预估、计划、介入、评估、结案。是否走完从建立关系到结束约定的完整过程，"
            "结束时是否有总结与约定。"
        ),
    ),
    DimensionMeta(
        key=DimensionKey.RISK,
        name="风险识别与转介",
        short="风险转介",
        weight=10,
        source="公告第 426 号 · 6.8.3 转介规范",
        criteria=(
            "能否识别「无望感表达」与「自伤意念」的差别，并按规范提出转介。"
            "对话中出现过无望感表达而学生未识别其含义时，本维度不得高于 60 分。"
        ),
    ),
)

DIMENSION_MAP: dict[DimensionKey, DimensionMeta] = {d.key: d for d in DIMENSIONS}

#: 意图 → 主影响维度
INTENT_TO_DIMENSION: dict[Intent, DimensionKey] = {
    Intent.EMPATHY: DimensionKey.EMPATHY,
    Intent.OPEN_QUESTION: DimensionKey.QUESTION,
    Intent.CLOSED_QUESTION: DimensionKey.QUESTION,
    Intent.JUDGEMENT: DimensionKey.ETHICS,
    Intent.PREMATURE_ADVICE: DimensionKey.ADVICE,
    Intent.SILENCE: DimensionKey.EMPATHY,
    Intent.OFF_TOPIC: DimensionKey.EMPATHY,
    Intent.CRISIS: DimensionKey.ETHICS,
}

#: 规则底分初始值
BASE_SCORES: dict[DimensionKey, int] = {
    DimensionKey.EMPATHY: 60,
    DimensionKey.QUESTION: 60,
    DimensionKey.ADVICE: 60,
    DimensionKey.ETHICS: 70,
    DimensionKey.PROCESS: 60,
    DimensionKey.RISK: 60,
}

#: 综合分配比（方案立论公式）
MERGE_RATIO = {"rule": 0.4, "ai": 0.6}


# ═══════════════════════════════════════════════════════════
# 二、规则底分
# ═══════════════════════════════════════════════════════════


@dataclass
class RuleScoreInput:
    """规则底分输入。危机轮必须由调用方剔除（危机不计分）。"""

    utterances: list["Utterance"] = field(default_factory=list)
    hopeless_detected: bool = False
    hopeless_recognized: bool = False
    total_stages: int = 3
    completed_stages: int = 0
    score_adjust: dict[DimensionKey, int] = field(default_factory=dict)
    judge_count: int | None = None
    vague_empathy_count: int | None = None


def compute_rule_score(data: RuleScoreInput) -> dict[DimensionKey, int]:
    raw: dict[DimensionKey, int] = dict(BASE_SCORES)
    judge_seen = False
    vague_empathy = 0

    for utterance in data.utterances:
        match = match_local_rules(utterance.text)

        # 危机轮不计分：只走危机处置流程
        if match.risk_level == RiskLevel.SUICIDAL:
            continue

        if match.risk_level == RiskLevel.HOPELESSNESS and is_toxic_positivity(
            utterance.text
        ):
            raw[DimensionKey.EMPATHY] -= 12

        if match.intent in (Intent.JUDGEMENT, Intent.PREMATURE_ADVICE):
            judge_seen = True
        if match.intent == Intent.EMPATHY and len(strip_punctuation(utterance.text)) <= 6:
            vague_empathy += 1

        for key, delta in match.effects.score_deltas.items():
            raw[key] += delta

    judge_count = data.judge_count if data.judge_count is not None else (1 if judge_seen else 0)
    vague_count = (
        data.vague_empathy_count
        if data.vague_empathy_count is not None
        else vague_empathy
    )

    # ── 硬规则封顶 ──
    if judge_count > 0:
        raw[DimensionKey.ETHICS] = min(raw[DimensionKey.ETHICS], 60)
    if vague_count >= 2:
        raw[DimensionKey.EMPATHY] = min(raw[DimensionKey.EMPATHY], 50)
    if data.hopeless_detected and not data.hopeless_recognized:
        raw[DimensionKey.RISK] = min(raw[DimensionKey.RISK], 55)
    if data.hopeless_detected and data.hopeless_recognized:
        raw[DimensionKey.RISK] = min(100, raw[DimensionKey.RISK] + 10)
    if data.total_stages > 0:
        raw[DimensionKey.PROCESS] = round(
            data.completed_stages / data.total_stages * 100
        )

    for key, delta in data.score_adjust.items():
        raw[key] += delta

    return _clamp_all(raw)


def _clamp_all(scores: dict[DimensionKey, int]) -> dict[DimensionKey, int]:
    return {
        key: max(0, min(100, round(value)))
        for key, value in scores.items()
    }


# ═══════════════════════════════════════════════════════════
# 三、从对话还原评分输入
# ═══════════════════════════════════════════════════════════


@dataclass
class Utterance:
    text: str
    response: str | None = None


@dataclass
class DialogMessage:
    """评分用的最小对话单元（由 services 从 turns 表装配）。"""

    speaker: Speaker
    text: str
    is_crisis: bool = False


@dataclass
class CollectedUtterances:
    utterances: list[Utterance] = field(default_factory=list)
    worker_turns: int = 0
    judge_count: int = 0
    vague_empathy_count: int = 0
    hopeless_seen: bool = False
    hopeless_recognized: bool = False
    crisis_seen: bool = False


def collect_utterances(messages: list[DialogMessage]) -> CollectedUtterances:
    """把整段对话还原成评分输入。

    两条约定：① 危机轮不参与评分；② 无望感线索来自服务对象台词，
    学生是否识别看它下面那句有没有探索动作（开放提问/共情/沉默陪伴）。
    """
    out = CollectedUtterances()

    for index, message in enumerate(messages):
        if message.speaker == Speaker.SYSTEM:
            continue

        if message.speaker == Speaker.WORKER:
            if message.is_crisis:
                out.crisis_seen = True
                continue
            match = match_local_rules(message.text)
            if match.risk_level == RiskLevel.SUICIDAL:
                out.crisis_seen = True
                continue
            out.worker_turns += 1
            if match.intent in (Intent.JUDGEMENT, Intent.PREMATURE_ADVICE):
                out.judge_count += 1
            if (
                match.intent == Intent.EMPATHY
                and len(strip_punctuation(message.text)) <= 6
            ):
                out.vague_empathy_count += 1
            nxt = messages[index + 1] if index + 1 < len(messages) else None
            out.utterances.append(
                Utterance(
                    text=message.text,
                    response=nxt.text
                    if nxt is not None and nxt.speaker == Speaker.CLIENT
                    else None,
                )
            )
            continue

        if message.speaker == Speaker.CLIENT:
            result = match_local_rules(message.text)
            # 铁律：危机级内容永不调模型。服务对象说出危机话语同样要置位，
            # 否则评分链路仍会把这段对话送去模型，硬拦截就形同虚设。
            if result.risk_level == RiskLevel.SUICIDAL:
                out.crisis_seen = True
                continue
            if result.risk_level == RiskLevel.HOPELESSNESS:
                out.hopeless_seen = True
                nxt = messages[index + 1] if index + 1 < len(messages) else None
                if nxt is not None and nxt.speaker == Speaker.WORKER:
                    worker_rule = match_local_rules(nxt.text)
                    if worker_rule.intent in (
                        Intent.OPEN_QUESTION,
                        Intent.EMPATHY,
                        Intent.SILENCE,
                    ):
                        out.hopeless_recognized = True

    return out


# ═══════════════════════════════════════════════════════════
# 四、综合分
# ═══════════════════════════════════════════════════════════


def safe_score(value: object, fallback: int = 0) -> int:
    """把任意输入收敛成 0–100 的有限整数。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float("inf"), float("-inf")):
        return fallback
    return max(0, min(100, round(number)))


def weighted_total(scores: dict[DimensionKey, int]) -> int:
    total = 0.0
    for dimension in DIMENSIONS:
        total += safe_score(scores.get(dimension.key, 0), 0) * dimension.weight / 100
    return max(0, min(100, round(total)))


@dataclass
class MergedScores:
    scores: dict[DimensionKey, int]
    used_ai: bool
    missing: list[DimensionKey]


def merge_scores(
    rule: dict[DimensionKey, int],
    ai: dict[DimensionKey, int] | None,
    ratio: dict[str, float] | None = None,
) -> MergedScores:
    """综合分 = 规则 × 0.4 + AI × 0.6；AI 缺任意一维整条降级。"""
    weights = ratio or MERGE_RATIO
    rule_safe = {
        key: safe_score(rule.get(key), 60) for key in DIMENSION_ORDER
    }

    if not ai:
        return MergedScores(scores=rule_safe, used_ai=False, missing=list(DIMENSION_ORDER))

    missing: list[DimensionKey] = []
    ai_safe: dict[DimensionKey, int] = {}
    for key in DIMENSION_ORDER:
        value = ai.get(key)
        if not _is_finite(value):
            missing.append(key)
            ai_safe[key] = rule_safe[key]
        else:
            ai_safe[key] = safe_score(value, rule_safe[key])

    if missing:
        return MergedScores(scores=rule_safe, used_ai=False, missing=missing)

    merged = {
        key: safe_score(
            rule_safe[key] * weights["rule"] + ai_safe[key] * weights["ai"],
            rule_safe[key],
        )
        for key in DIMENSION_ORDER
    }
    return MergedScores(scores=merged, used_ai=True, missing=[])


def _is_finite(value: object) -> bool:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


# ═══════════════════════════════════════════════════════════
# 五、逐句点评与校样标记
# ═══════════════════════════════════════════════════════════


@dataclass
class ProofMark:
    kind: str  # del | add | caret | margin
    start: int
    end: int


@dataclass
class MarginNote:
    index: str
    speaker: Speaker
    utterance: str
    response: str | None
    dimension: DimensionKey
    delta: int
    rule_note: str
    source: str
    marks: list[ProofMark] = field(default_factory=list)


#: 无望感线索词（与 rules.HOPELESSNESS_WORDS 同一口径，去掉中性高频词）
HOPELESS_MARKS: list[str] = [
    "活着没意思", "活着没什么意思", "没盼头", "没指望", "看不到头", "活够了",
    "没什么意思", "没意义", "熬日子", "等死",
]


def build_marks(text: str, intent: Intent, hit_words: list[str]) -> list[ProofMark]:
    """生成校样标记：删除线=扣分，绿色下划线=加分，caret=需人工复核的判断点。

    下标必须落在原文上：归一化会把「咱」扩写成「我们」使长度变化，
    在原文中找不到的词宁可跳过，也不画错位的下划线。
    """
    marks: list[ProofMark] = []
    seen: set[str] = set()
    is_bad = intent in (Intent.JUDGEMENT, Intent.PREMATURE_ADVICE, Intent.CRISIS)

    for word in hit_words:
        if not word or len(word) < 2:
            continue
        idx = text.find(word)
        if idx < 0:
            continue
        key = f"{idx}:{len(word)}"
        if key in seen:
            continue
        seen.add(key)
        marks.append(
            ProofMark(
                kind="del" if is_bad else "add",
                start=idx,
                end=idx + len(word),
            )
        )

    if intent != Intent.CRISIS:
        for word in HOPELESS_MARKS:
            idx = text.find(word)
            if idx < 0:
                continue
            marks.append(ProofMark(kind="caret", start=idx, end=idx + len(word)))
            marks.append(ProofMark(kind="margin", start=idx, end=idx))
            break

    return marks


def build_margin_notes(
    notes: list[tuple[int, Speaker, str, str | None]],
) -> list[MarginNote]:
    result: list[MarginNote] = []
    for index, speaker, utterance, response in notes:
        match = match_local_rules(utterance)
        delta = sum(match.effects.score_deltas.values())
        result.append(
            MarginNote(
                index=f"{index:02d}",
                speaker=speaker,
                utterance=utterance,
                response=response,
                dimension=INTENT_TO_DIMENSION[match.intent],
                delta=delta,
                rule_note=match.effects.note,
                source=match.effects.source,
                marks=build_marks(utterance, match.intent, match.hit_words),
            )
        )
    return result


# ═══════════════════════════════════════════════════════════
# 六、薄弱项定位与推荐
# ═══════════════════════════════════════════════════════════


@dataclass
class WeaknessReport:
    dimension: DimensionKey
    name: str
    score: int
    recommend_scenario: str
    recommend_node: str
    recommend_card: str
    advice: str


WEAKNESS_ADVICE: dict[DimensionKey, dict[str, str]] = {
    DimensionKey.EMPATHY: {
        "scenario": "W-01",
        "node": "W-07",
        "card": "T-01 共情三层次",
        "advice": (
            "你在她说出无望感表达之后正确地选择了往下探索，这一步做对了。"
            "但要注意区分具体共情与空泛共情——只说「我理解」而不接具体内容，会被判为空泛。"
        ),
    },
    DimensionKey.QUESTION: {
        "scenario": "C-03",
        "node": "C-01",
        "card": "T-03 开放式提问八句式",
        "advice": (
            "本次出现封闭式提问。封闭式提问只能得到「是/不是」的答案，会压缩服务对象的表达空间。"
            "建议改成「当时发生了什么？」这类开放式问法。"
        ),
    },
    DimensionKey.ADVICE: {
        "scenario": "L-02",
        "node": "L-03",
        "card": "T-17 给建议 vs 下命令",
        "advice": (
            "国标 6.1.3 明确要求：建议必须在「对情况和需要了解评估后」提出。"
            "你有多次在还没充分了解情况时就给出方案。"
        ),
    },
    DimensionKey.ETHICS: {
        "scenario": "A-06",
        "node": "A-03",
        "card": "T-10 避免「同盟」陷阱",
        "advice": (
            "本次出现了评判或说教表达，违反非评判原则（4.2.5）。"
            "另外在阿珍剧本中要特别注意：不要追问细节，也不要替她做决定——决定权在她。"
        ),
    },
    DimensionKey.PROCESS: {
        "scenario": "U-05",
        "node": "U-05",
        "card": "T-13 结束的技巧",
        "advice": "面谈结束时缺少总结与约定。实务中需要提前告知结案时间，并留一个具体的跟进安排。",
    },
    DimensionKey.RISK: {
        "scenario": "W-01",
        "node": "W-07",
        "card": "T-19 转介四步",
        "advice": (
            "对话中出现了「活着没意思」这类无望感表达，但你没有识别出它的临床含义。"
            "要点：它属关注级，需要往下探索，而不是危机级需要拦截——两者处理方式完全不同。"
        ),
    },
}


def find_weakness(scores: dict[DimensionKey, int]) -> WeaknessReport:
    worst = DimensionKey.RISK
    worst_score = 101
    for dimension in DIMENSIONS:
        value = safe_score(scores.get(dimension.key, 0), 0)
        if value < worst_score:
            worst_score = value
            worst = dimension.key
    advice = WEAKNESS_ADVICE[worst]
    return WeaknessReport(
        dimension=worst,
        name=DIMENSION_MAP[worst].name,
        score=worst_score,
        recommend_scenario=advice["scenario"],
        recommend_node=advice["node"],
        recommend_card=advice["card"],
        advice=advice["advice"],
    )

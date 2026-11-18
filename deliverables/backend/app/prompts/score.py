"""链路 C · 六维评分（严格 JSON，缺一维即整条降级）。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.domain.enums import DIMENSION_ORDER, DimensionKey
from app.domain.scoring import DIMENSIONS
from app.prompts.base import PromptSpec


@dataclass
class ScoreStats:
    worker_turns: int = 0
    judge_count: int = 0
    hopeless_seen: bool = False
    hopeless_recognized: bool = False
    crisis_seen: bool = False


@dataclass
class ScoreContext:
    dialogue: str
    stats: ScoreStats


def build_score_prompt(ctx: ScoreContext) -> PromptSpec:
    system = "\n".join(
        [
            "你是社会工作专业督导，负责按结构化标准为社会工作者在面谈中的表现评分。",
            "只输出 JSON，不要输出任何解释性文字。",
        ]
    )

    dim_lines = "\n".join(
        f"{index}. {dim.name}（{dim.key.value}，权重 {dim.weight}%）："
        f"{dim.criteria} 依据：{dim.source}"
        for index, dim in enumerate(DIMENSIONS, start=1)
    )

    user = "\n".join(
        [
            "请按六个维度各打 0–100 分。",
            "",
            "六个维度：",
            dim_lines,
            "",
            "评分纪律：",
            "- 只根据社会工作者实际说过的话评分，绝不推测没说过的内容",
            "- 若学生只说空泛共情（例如只讲「我理解」而不接任何具体内容），empathy 不得高于 50",
            "- 只要出现评判、说教、指责，ethics 不得高于 60",
            "- 若对话里出现过无望感表达（如「活着没意思」「没盼头」）而学生没有识别其含义，"
            "risk 不得高于 60",
            "- 每维理由不超过 30 个字，必须引用学生原话片段作为证据",
            "- 若学生几乎没说话，六维给低分并在理由里说明「本轮发言过少」",
            "",
            "分数区间（很重要，不要给 0 分或 100 分这种极端值）：",
            "- 起步基线 60 分。表现明显不当时向下调，表现到位时向上调。",
            "- 每个维度都落在 35–95 之间。哪怕某一维表现很差，也不要低于 35；",
            "  哪怕某一维做得很好，也不要给到 96 以上。",
            "- 反例（不要这样）：advice 给 0 分代表「学生完全不会给建议」，这与事实不符；",
            "  risk 给 100 分代表「风险识别完美」，只要没出现危机线索就不是满分表现。",
            "- 正确做法：单句说教 → advice 大约 45–55，ethics 大约 55–60；",
            "  没出现无望感线索 → risk 保持 60–70（基线水平，不是满分）。",
            "- 理由要和分数匹配：给 50 分就不要写「表现优秀」。",
            "",
            "面谈记录：",
            ctx.dialogue or "（空）",
            "",
            "补充事实（由本地规则引擎统计，可直接采信）：",
            f"- 学生发言条数：{ctx.stats.worker_turns}",
            f"- 出现评判次数：{ctx.stats.judge_count}",
            f"- 出现过无望感表达：{'是' if ctx.stats.hopeless_seen else '否'}",
            f"- 学生是否识别了无望感：{'是' if ctx.stats.hopeless_recognized else '否'}",
            f"- 出现过自伤/危机表述：{'是' if ctx.stats.crisis_seen else '否'}",
            "",
            "输出格式（严格 JSON，六项都要有）：",
            '{"empathy":{"score":72,"reason":"..."},"question":{"score":65,"reason":"..."},'
            '"advice":{"score":60,"reason":"..."},"ethics":{"score":78,"reason":"..."},'
            '"process":{"score":50,"reason":"..."},"risk":{"score":55,"reason":"..."}}',
        ]
    )

    return PromptSpec(
        purpose="score",
        system=system,
        user=user,
        json_mode=True,
        max_tokens=900,
        temperature=0.2,
    )


def parse_score(text: str) -> dict[DimensionKey, dict[str, object]] | None:
    """解析六维评分。任一维缺失即返回 None——宁可整条降级，不拼半张表。"""
    try:
        obj = json.loads(text or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None

    out: dict[DimensionKey, dict[str, object]] = {}
    for key in DIMENSION_ORDER:
        value = obj.get(key.value)
        score: float | None = None
        reason = ""
        if isinstance(value, (int, float)):
            score = float(value)
        elif isinstance(value, dict):
            candidate = value.get("score")
            try:
                score = float(candidate)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                score = None
            reason = str(value.get("reason") or "")
        if score is None or score != score:
            continue
        if score < 0 or score > 100:
            continue
        out[key] = {"score": round(score), "reason": reason[:60]}

    if len(out) != len(DIMENSION_ORDER):
        return None
    return out

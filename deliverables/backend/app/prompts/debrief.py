"""链路 D · 复盘报告（三段式，去营销词）。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.domain.enums import DimensionKey
from app.domain.scoring import DIMENSIONS
from app.prompts.base import PromptSpec

#: 营销黑话黑名单（成品里出现即删除，避免复盘读起来像 PPT）
BANNED_WORDS: tuple[str, ...] = (
    "赋能",
    "闭环",
    "底层逻辑",
    "抓手",
    "颗粒度",
    "组合拳",
)


@dataclass
class DebriefContext:
    nickname: str = "同学"
    name: str = "未知"
    age: int | None = None
    identity: str = ""
    scores: dict[DimensionKey, int] | None = None
    hit_rules: list[str] | None = None


def build_debrief_prompt(ctx: DebriefContext) -> PromptSpec:
    system = "你是社会工作专业督导，负责为学生写一份面谈复盘。只输出 JSON。"

    scores = ctx.scores or {}
    score_line = "、".join(
        f"{dim.name} {scores.get(dim.key, '—')}" for dim in DIMENSIONS
    )

    hit_rules = ctx.hit_rules or []
    user = "\n".join(
        [
            "请写三段复盘，用 JSON 返回。",
            "",
            "strength：写 1–2 处学生处理得当的地方，必须引用学生的原话作为证据",
            "improvement：写 1–2 处问题，说明违反了哪一条专业原则",
            "nextStep：给 2–3 条可操作的练习建议",
            "",
            "文风要求：平实、不说教、不打鸡血、不喊口号；"
            "禁止出现「赋能」「闭环」「底层逻辑」「抓手」这类词；不要使用心理诊断词汇。",
            "每段 60–120 字。",
            "",
            f"学生昵称：{ctx.nickname or '同学'}",
            f"服务对象：{ctx.name}，{ctx.age if ctx.age is not None else '?'}岁，{ctx.identity}",
            f"本阶段六维：{score_line}",
            "本阶段命中的规则记录：",
            "\n".join(hit_rules) if hit_rules else "（本次未触发特殊规则）",
            "",
            '输出格式：{"strength":"...","improvement":"...","nextStep":"..."}',
        ]
    )

    return PromptSpec(
        purpose="debrief",
        system=system,
        user=user,
        json_mode=True,
        max_tokens=700,
        temperature=0.4,
    )


def parse_debrief(text: str) -> dict[str, str] | None:
    """解析复盘三段；任一段为空或 nextStep 过短即整条判废。"""
    try:
        obj = json.loads(text or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None

    def pick(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    out = {
        "strength": pick(obj.get("strength")),
        "improvement": pick(obj.get("improvement")),
        "next_step": pick(obj.get("nextStep")),
    }
    if not out["strength"] or not out["improvement"] or not out["next_step"]:
        return None
    if len(out["next_step"]) < 10:
        return None

    for key in list(out):
        value = out[key][:320]
        for word in BANNED_WORDS:
            value = value.replace(word, "")
        out[key] = value
    return out

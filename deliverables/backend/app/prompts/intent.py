"""链路 A · 意图分类（低延迟、强约束、可被规则覆盖）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Intent
from app.prompts.base import PromptSpec, strip_punctuation

INTENT_ENUM: tuple[str, ...] = tuple(item.value for item in Intent)

INTENT_GUIDE: tuple[str, ...] = (
    "共情：接住了对方的具体情绪或处境，例如「听起来一个人过日子挺难的」",
    "开放提问：用「什么/怎么/能不能说说」等引导对方展开",
    "封闭提问：只能回答是或否，例如「是不是」「对不对」「有没有」",
    "评判：评价、指责、说教、否定对方感受，例如「你应该」「别想太多」",
    "建议过早：尚未充分了解情况就直接给方案、给办法",
    "沉默陪伴：表示愿意等待、不催促、不打断",
    "离题：与当前议题无关的内容",
    "危机：涉及自伤或他伤的表述",
)


@dataclass
class IntentContext:
    input_text: str
    stage: str = "未知"
    name: str = "未知"
    age: int | None = None
    identity: str = ""
    brief: str = ""
    rule_hint: str = "未命中规则"


def build_intent_prompt(ctx: IntentContext) -> PromptSpec:
    system = "\n".join(
        [
            "你是社会工作面谈的观察员。你的唯一任务是判断「学生（社会工作者）」"
            "刚说的这句话属于哪一类意图。",
            "只输出 JSON，不要输出任何解释。",
        ]
    )

    user = "\n".join(
        [
            "八个类别（只能选一个）：" + "、".join(INTENT_ENUM),
            "",
            "判定要点：",
            *[f"- {line}" for line in INTENT_GUIDE],
            "",
            f"当前阶段：{ctx.stage}",
            f"服务对象：{ctx.name}，{ctx.age if ctx.age is not None else '?'}岁，{ctx.identity}",
            f"主诉：{ctx.brief}",
            f"本地规则给出的初判：{ctx.rule_hint}",
            "",
            f"学生刚说的话：{ctx.input_text}",
            "",
            '输出格式：{"intent":"共情"}',
            f"intent 必须是以下之一：{'|'.join(INTENT_ENUM)}",
        ]
    )

    return PromptSpec(
        purpose="intent",
        system=system,
        user=user,
        json_mode=True,
        max_tokens=60,
        temperature=0.0,
    )


def parse_intent(text: str) -> Intent | None:
    """从模型输出里抽出意图标签；抽不出返回 None，由调用方回落到规则初判。"""
    import json

    raw = text or ""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        obj = None

    if isinstance(obj, dict):
        raw = str(obj.get("intent") or "")

    bare = strip_punctuation(raw)
    for intent in Intent:
        if intent.value in bare:
            return intent
    return None

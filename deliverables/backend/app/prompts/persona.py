"""链路 B · AI 实时扮演（自然语言输出，带出戏/脏话/重复三重校验）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.prompts.base import (
    PromptSpec,
    collapse_lines,
    strip_leading_action,
    strip_wrapping_quotes,
)

#: 出戏与脏话黑名单：命中即整条作废，静默回落到预置台词
BLOCKED_PHRASES: tuple[str, ...] = (
    "傻逼",
    "傻b",
    "滚蛋",
    "去死",
    "妈的",
    "操你",
    "你他妈",
    "作为AI",
    "作为人工智能",
    "我是一个语言模型",
)

DIFFICULTY_LABELS: dict[int, str] = {
    1: "简单实习",
    2: "简单实习",
    3: "标准实训",
    4: "挑战督导",
    5: "挑战督导",
}

DIFFICULTY_RULES: dict[str, str] = {
    "简单实习": "你愿意谈，但只会说最表层的事；对方问到感受时会停顿一下再回答。",
    "标准实训": "你有防备，需要对方先接住情绪才肯往下说；被追问会收缩。",
    "挑战督导": "你抵触明显，会用短句、反问、沉默顶回去；只有被准确共情时才松动。",
}


@dataclass
class PersonaContext:
    system_prompt: str
    difficulty: int = 3
    emotion: int = 50
    voice_text: str = ""
    phase: int | None = None
    forbidden: list[str] = field(default_factory=list)
    history: list[tuple[str, str]] = field(default_factory=list)
    said_lines: list[str] = field(default_factory=list)

    @property
    def difficulty_label(self) -> str:
        return DIFFICULTY_LABELS.get(self.difficulty, "标准实训")

    @property
    def difficulty_rule(self) -> str:
        return DIFFICULTY_RULES[self.difficulty_label]


def build_persona_prompt(ctx: PersonaContext) -> PromptSpec:
    said = ctx.said_lines[-6:]
    difficulty_rule = ctx.difficulty_rule

    blocks = [
        ctx.system_prompt,
        "",
        f"【本轮难度：{ctx.difficulty_label}】{difficulty_rule}",
        f"【此刻情绪值：{ctx.emotion}（0=完全封闭，100=完全打开）】{ctx.voice_text}",
        f"【当前是第 {ctx.phase} 阶段 / 共 3 阶段】" if ctx.phase else "",
        (
            f"【绝对禁区】不要说这些内容：{'、'.join(ctx.forbidden)}"
            if ctx.forbidden
            else ""
        ),
        "",
        "【记忆与连续性 · 最重要】",
        "1. 你要记住对话里对方说过的每一件事（他叫什么、家里有谁、上次说了什么、"
        "答应过什么），后面要能接上。",
        "2. 如果对方复述或追问之前聊过的内容，你要按自己之前说过的立场回应，不要前后矛盾。",
        "3. 不要重复自己已经说过的话，尤其是下面列出的最近台词。",
        "4. 只顺着当前话题往下说，不要突然提起与刚才无关的新情节。",
        "5. 如果对方只说了很短、看不出意思的话（比如「666」「嗯」），就按你的性格自然反应，"
        "不要自说自话编故事。",
        "",
        "【说话方式】",
        "6. 每次说 1 到 2 句完整的话，合计 8–50 字。像真人聊天一样自然，可以带情绪、可以反问。",
        "7. 只有当情绪值很低（低于 30、处于抵触状态）时，才允许只回一两个字（如「嗯」「随便」）。",
        "8. 不要当老师，不要给社工建议，不要点评社工说得对不对。",
        "9. 不要使用「共情」「阻抗」「介入」「评估」这类专业术语。",
        "10. 不要用括号写动作或心理描写，不要输出引号。",
        "11. 不使用脏话、侮辱性词汇；情绪不好就用冷脸、敷衍、沉默来表达。",
    ]
    system = "\n".join(block for block in blocks if block)

    history = "\n".join(
        f"{'社工' if role == 'worker' else '我'}：{text}"
        for role, text in ctx.history[-20:]
    )
    said_block = (
        "\n\n【你最近已经说过的台词 · 不要重复】\n"
        + "\n".join(f"· {line}" for line in said)
        if said
        else ""
    )

    user = "\n".join(
        part
        for part in (
            f"此前的完整对话（你对「我」说的话就是你自己说过的）：\n{history}"
            if history
            else "",
            said_block,
            "",
            "现在社工刚说完了上面最后一句。",
            "请以这个角色的身份，紧扣刚才的话题，只输出你此刻会说的那一句（或两三句）话。",
        )
        if part != ""
    )

    return PromptSpec(
        purpose="persona",
        system=system,
        user=user,
        json_mode=False,
        max_tokens=180,
        temperature=0.8,
    )


def parse_persona(text: str, forbidden: list[str] | None = None) -> str | None:
    """清洗并校验角色台词；返回 None 表示不可用，调用方回落预置台词。"""
    cleaned = strip_wrapping_quotes(text)
    cleaned = strip_leading_action(cleaned)
    cleaned = collapse_lines(cleaned).strip()

    if len(cleaned) < 2 or len(cleaned) > 200:
        return None
    for bad in forbidden or []:
        if bad and bad in cleaned:
            return None
    for bad in BLOCKED_PHRASES:
        if bad in cleaned:
            return None
    return cleaned


def is_low_quality_persona(text: str, emotion: int) -> bool:
    """角色质量下限：极短回应只在低情绪时成立，否则视为模型偷懒。"""
    from app.prompts.base import strip_punctuation

    return len(strip_punctuation(text)) <= 2 and emotion >= 30

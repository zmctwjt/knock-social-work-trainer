"""提示词公共骨架：版本号、请求规格与文本清洗工具。

`PROMPT_VERSION` 是本模块唯一的版本出口：它同时进入
① AI 缓存键（换提示词即换缓存，旧结果不会串味）
② `ai_audit_log.prompt_version`（复盘时可回答"这条结果出自哪版提示词"）。
修改任何一条提示词的措辞都必须提升版本号，否则缓存会返回旧口径的结果。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: 提示词版本（2026-11 首版）。改动提示词即提升。
PROMPT_VERSION = "2026.11.1"

#: 参与缓存的链路 → 版本快照
PROMPT_VERSIONS: dict[str, str] = {
    "intent": PROMPT_VERSION,
    "persona": PROMPT_VERSION,
    "score": PROMPT_VERSION,
    "debrief": PROMPT_VERSION,
}


@dataclass(frozen=True)
class PromptSpec:
    """一次模型调用的完整规格（与厂商无关）。"""

    purpose: str
    system: str
    user: str
    json_mode: bool = False
    max_tokens: int = 400
    temperature: float = 0.3

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSIONS.get(self.purpose, PROMPT_VERSION)


_PUNCT = re.compile(r"[\s\"'，。！？、；：（）()【】「」『』“”‘’·…—]+")


def strip_punctuation(text: str) -> str:
    """去掉空白与中英文标点，用于宽松匹配模型输出。"""
    return _PUNCT.sub("", text or "")


def collapse_lines(text: str) -> str:
    """把多行文本并成一句，避免角色气泡被换行撑开。"""
    return re.sub(r"\s*\n+\s*", "　", (text or "").strip())


def strip_wrapping_quotes(text: str) -> str:
    return re.sub(
        r"^[\s\"'“”『』「」]+|[\s\"'“”『』「」]+$",
        "",
        text or "",
    )


def strip_leading_action(text: str) -> str:
    """去掉行首的括号动作描写，例如「（叹气）你说吧」。"""
    return re.sub(r"^[（(][^）)]*[）)]\s*", "", text or "")

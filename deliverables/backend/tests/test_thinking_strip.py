"""思维链剥离与空内容判定。

起因：接入真实密钥后用三个模型实测发现
- glm-4.7-flash 是推理模型，传 thinking=disabled 能正常关闭思考；
- glm-z1-flash **不受 thinking 参数控制**，会把 `<think>…</think>`
  混进 content。不剥离的话，服务对象会把内心独白说给学生听。
- 未关闭思考时 content 可能为空串而 finish_reason=length，
  把空串当成功会让"服务对象一言不发"。

这组测试锁住这两个行为。
"""

from __future__ import annotations

import pytest

from app.services.llm.base import ProviderError
from app.services.llm.openai_compat import OpenAICompatProvider, strip_thinking


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>内心活动</think>最终回复", "最终回复"),
        ("前言<think>中间思考</think>后文", "前言后文"),
        ("<think>被截断的思考", ""),
        ("<THINK>大写标签</THINK>正文", "正文"),
        ("<think\n>多行\n思考</think\n>正文", "正文"),
        ("没有思考标签的普通文本", "没有思考标签的普通文本"),
        ("  <think>x</think>  ", ""),
    ],
)
def test_strip_thinking(raw, expected):
    assert strip_thinking(raw) == expected


def _provider() -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="http://unused", api_key="k", timeout_ms=1000
    )


def _payload(content: str, *, reasoning: str = "", text_field: str | None = None):
    message: dict = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    first: dict = {"message": message}
    if text_field is not None:
        first["text"] = text_field
    return {"choices": [first]}


def test_extract_text_strips_thinking_tags():
    p = _provider()
    got = p._extract_text(_payload("<think>想一下</think>您好，我是小陈。"))
    assert got == "您好，我是小陈。"


def test_empty_content_raises_instead_of_returning_blank():
    """空正文必须抛错——否则上层会拿到空回复当成成功。"""
    p = _provider()
    with pytest.raises(ProviderError) as exc:
        p._extract_text(_payload("", reasoning="思考了一百字但没有正文"))
    msg = str(exc.value)
    assert ("正文" in msg or "思考过程" in msg), f"错误信息应说明原因，实际：{msg}"


def test_only_thinking_counts_as_empty():
    """只有思考链、剥离后为空，同样视为失败。"""
    p = _provider()
    with pytest.raises(ProviderError):
        p._extract_text(_payload("<think>全是思考</think>"))


def test_fallback_to_text_field():
    """少数兼容实现把内容放在 text 字段。"""
    p = _provider()
    got = p._extract_text(_payload("", text_field="来自 text 字段"))
    assert got == "来自 text 字段"


def test_missing_choices_raises():
    p = _provider()
    with pytest.raises(ProviderError):
        p._extract_text({"choices": []})

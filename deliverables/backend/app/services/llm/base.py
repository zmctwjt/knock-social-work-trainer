"""LLM 供应商抽象层。

只定义两件事：请求长什么样、失败分几类。
"哪些失败可以换模型重试"是网关铁律的落点——只有 429（含平台码 1305）、
5xx、超时算可重试；鉴权失败、参数错误、空回复都不换模型，
直接整条链路降级到规则，避免把故障放大成三倍调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMRequest:
    model: str
    messages: list[LLMMessage]
    max_tokens: int = 400
    temperature: float = 0.3
    json_mode: bool = False
    timeout_ms: int = 45_000
    purpose: str = "intent"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class ProviderError(Exception):
    """供应商侧失败。`retryable` 决定"重试 + 换模型"还是"立即降级"。"""

    def __init__(
        self,
        reason: str,
        *,
        retryable: bool,
        status: int | None = None,
        detail: str = "",
    ) -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.retryable = retryable
        self.status = status
        self.detail = detail

    @classmethod
    def timeout(cls, detail: str = "") -> "ProviderError":
        return cls("timeout", retryable=True, detail=detail)

    @classmethod
    def rate_limited(cls, status: int = 429, detail: str = "") -> "ProviderError":
        return cls("rate_limited", retryable=True, status=status, detail=detail)

    @classmethod
    def server_error(cls, status: int, detail: str = "") -> "ProviderError":
        return cls("server_error", retryable=True, status=status, detail=detail)

    @classmethod
    def network(cls, detail: str = "") -> "ProviderError":
        return cls("network", retryable=True, detail=detail)

    @classmethod
    def auth(cls, status: int = 401, detail: str = "") -> "ProviderError":
        return cls("auth", retryable=False, status=status, detail=detail)

    @classmethod
    def bad_request(cls, status: int = 400, detail: str = "") -> "ProviderError":
        return cls("bad_request", retryable=False, status=status, detail=detail)

    @classmethod
    def empty(cls, detail: str = "模型返回空内容") -> "ProviderError":
        return cls("empty", retryable=False, detail=detail)

    @classmethod
    def bad_payload(cls, detail: str = "响应体不是预期结构") -> "ProviderError":
        return cls("bad_payload", retryable=False, detail=detail)


class AllModelsFailed(Exception):
    """整条模型链都失败。异常携带最后一次失败原因，供降级指标使用。"""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@runtime_checkable
class LLMProvider(Protocol):
    """供应商协议。测试里可以直接替换成记录调用的假实现。"""

    name: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    async def close(self) -> None: ...

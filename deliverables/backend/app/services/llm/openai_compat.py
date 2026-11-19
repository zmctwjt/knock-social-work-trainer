"""OpenAI 兼容 Chat Completions 供应商（智谱、DeepSeek 等共用）。

请求体与旧 Node 版保持一致：`temperature` 默认 0.3、`thinking` 由子类决定、
JSON 输出用 `response_format={"type":"json_object"}`。
错误分类见 `ProviderError`：只有 429 / 5xx / 超时可重试。
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.services.llm.base import (
    LLMRequest,
    LLMResponse,
    ProviderError,
)


#: 成对的思维链标签。实测 `glm-z1-flash` 即使传 thinking=disabled
#: 也会把思考过程混进 content（其它两个模型能正常关闭）。
#: 不剥离的话，服务对象会把内心独白直接说给学生听。
_THINK_PAIR = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
#: 未闭合的思维链（被 max_tokens 截断的情况）：从 <think 起到结尾全部丢弃
_THINK_OPEN = re.compile(r"<think\b[^>]*>.*$", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """去掉模型输出里的思维链标记，只留正文。"""
    cleaned = _THINK_PAIR.sub("", text)
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


class OpenAICompatProvider:
    name = "openai-compat"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_ms: int = 45_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_ms = timeout_ms
        self._client = client
        self._owns_client = client is None

    # ── 客户端生命周期 ──
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_ms / 1000),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    # ── 请求体 ──
    def _build_body(self, request: LLMRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [message.as_dict() for message in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # ── 调用 ──
    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = await self._get_client()
        body = self._build_body(request)
        started = time.perf_counter()

        try:
            response = await client.post(
                self.base_url,
                json=body,
                headers=self._headers(),
                timeout=httpx.Timeout(
                    (request.timeout_ms or self.timeout_ms) / 1000
                ),
            )
        except httpx.TimeoutException as exc:
            raise ProviderError.timeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ProviderError.network(str(exc)) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError.bad_payload("响应体不是合法 JSON") from exc

        self._raise_for_platform_error(payload)
        text = self._extract_text(payload)
        if not text.strip():
            raise ProviderError.empty()

        usage = payload.get("usage") or {}
        return LLMResponse(
            text=text,
            model=str(payload.get("model") or request.model),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
        )

    # ── 错误翻译 ──
    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        detail = response.text[:300]
        if status == 429:
            raise ProviderError.rate_limited(status, detail)
        if status >= 500:
            raise ProviderError.server_error(status, detail)
        if status in (401, 403):
            raise ProviderError.auth(status, detail)
        raise ProviderError.bad_request(status, detail)

    def _raise_for_platform_error(self, payload: dict[str, Any]) -> None:
        """平台可能用 HTTP 200 返回错误体，例如智谱 1305（并发过高）。"""
        error = payload.get("error")
        if not error:
            return
        code = error.get("code") if isinstance(error, dict) else None
        message = str(error.get("message", "")) if isinstance(error, dict) else str(error)
        if str(code) in ("1305", "1302", "429"):
            raise ProviderError.rate_limited(429, message)
        if str(code) in ("1000", "1001", "1002", "1003", "1004"):
            raise ProviderError.auth(401, message)
        raise ProviderError.bad_request(400, f"platform code={code} {message}")

    def _extract_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError.bad_payload("choices 为空")
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") or {}
        content = message.get("content")
        # 空串也算"没有内容"，要允许回落到 text 字段再判定失败
        raw = content if isinstance(content, str) and content.strip() else None
        alt = first.get("text")
        if raw is None and isinstance(alt, str) and alt.strip():
            # 少数兼容实现把内容放在 text 字段
            raw = alt
        if raw is None:
            reasoning = message.get("reasoning_content") or ""
            raise ProviderError.bad_payload(
                f"模型未返回正文（reasoning {len(reasoning)} 字）"
            )

        text = strip_thinking(raw)
        if not text:
            # 不能把空串当成功：推理模型可能把 token 全花在 reasoning_content
            # 上（实测 glm-4.7-flash 未关闭 thinking 时就是 content=""），
            # 空内容交给上层会变成"服务对象一言不发"这种不可解释的现象。
            # 抛错让路由层切下一个模型或降级到规则。
            reasoning = message.get("reasoning_content") or ""
            raise ProviderError.bad_payload(
                f"模型只输出了思考过程，正文为空（reasoning {len(reasoning)} 字）"
            )
        return text

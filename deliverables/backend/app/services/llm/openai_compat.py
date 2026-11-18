"""OpenAI 兼容 Chat Completions 供应商（智谱、DeepSeek 等共用）。

请求体与旧 Node 版保持一致：`temperature` 默认 0.3、`thinking` 由子类决定、
JSON 输出用 `response_format={"type":"json_object"}`。
错误分类见 `ProviderError`：只有 429 / 5xx / 超时可重试。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.services.llm.base import (
    LLMRequest,
    LLMResponse,
    ProviderError,
)


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
        if isinstance(content, str):
            return content
        # 少数兼容实现把内容放在 delta / text 字段
        if isinstance(first.get("text"), str):
            return str(first["text"])
        raise ProviderError.bad_payload("message.content 不是字符串")

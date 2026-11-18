"""智谱 GLM 供应商（OpenAI 兼容端点 + thinking disabled）。

模型链与旧实现一致：glm-4.7-flash → glm-4.5-flash → glm-4-flash。
`thinking: {"type": "disabled"}` 是必须继承的线上参数：开启思考链会把
单次延迟推高到 10s 以上，而四条链路的输出都不需要推理过程。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.services.llm.base import LLMRequest
from app.services.llm.openai_compat import OpenAICompatProvider

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


class ZhipuProvider(OpenAICompatProvider):
    name = "zhipu"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url=settings.glm_base_url or DEFAULT_BASE_URL,
            api_key=settings.glm_api_key,
            timeout_ms=settings.glm_timeout_ms,
            client=client,
        )
        self.settings = settings

    def _build_body(self, request: LLMRequest) -> dict[str, Any]:
        body = super()._build_body(request)
        # 继承线上参数：关闭思考链，保证 P95 可控
        body["thinking"] = {"type": "disabled"}
        return body

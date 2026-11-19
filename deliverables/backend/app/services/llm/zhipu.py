"""智谱 GLM 供应商（OpenAI 兼容端点 + thinking disabled）。

模型链按**实测延迟**排序，不是按版本新旧：
glm-4-flash-250414（中位 865ms）→ glm-z1-flash（2.1s）→ glm-4.7-flash（21.3s）。

glm-4.7-flash 虽然版本更新，但它是推理模型：即使传
`thinking: {"type": "disabled"}`，实测冷调用仍要 10–32 秒，
且并发时会返回 429。面谈训练是实时对话，等 20 秒才出一句
服务对象台词不可接受，因此排在最后作为兜底而非主选。

`thinking: {"type": "disabled"}` 仍必须传：对 glm-4.7-flash 有效
（关闭后正文正常），对 glm-z1-flash 无效（它会把 `<think>` 混进
正文，由 openai_compat.strip_thinking 负责剥离）。
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

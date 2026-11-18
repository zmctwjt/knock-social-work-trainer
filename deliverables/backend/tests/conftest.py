"""测试夹具。

三条硬约束决定这里的设计：
1. 不依赖真实 PG/Redis/外网 —— 用 SQLite 内存库 + 内存 KV + 假模型供应商；
2. 每个用例独立 app 实例 —— 限流窗口、缓存、熔断器互不污染；
3. lifespan 必须真的执行 —— 用 `app.router.lifespan_context()` 手动进出，
   这样建表、种子数据、依赖装配都走生产同一条代码路径。
"""

from __future__ import annotations

import os

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite+aiosqlite://",
        "AUTO_CREATE_SCHEMA": "true",
        "SEED_SCENARIOS_ON_STARTUP": "true",
        "REDIS_URL": "",
        "RATE_LIMIT_ENABLED": "false",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "GLM_API_KEY": "",
        "JWT_SECRET": "test-secret-0123456789abcdef0123456789",
        "OTEL_ENABLED": "false",
        "ARGON2_TIME_COST": "1",
        "ARGON2_MEMORY_COST": "8192",
        "ARGON2_PARALLELISM": "1",
    }
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.services.llm.base import LLMResponse, ProviderError


class FakeProvider:
    """可编排的假供应商：按顺序吐出文本或抛错，并记录每次请求。"""

    name = "fake"

    def __init__(self, responses=(), errors=()) -> None:
        self.responses = list(responses)
        self.errors = list(errors)
        self.calls: list = []

    async def complete(self, request):
        self.calls.append(request)
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        text = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(
            text=text,
            model=request.model,
            tokens_in=12,
            tokens_out=8,
            latency_ms=5,
        )

    async def close(self) -> None:
        pass


@pytest_asyncio.fixture
async def app_factory():
    contexts = []

    async def _make(**overrides):
        settings = Settings(_env_file=None, **overrides)
        application = create_app(settings)
        context = application.router.lifespan_context(application)
        await context.__aenter__()
        contexts.append(context)
        return application

    yield _make

    for context in reversed(contexts):
        await context.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def client_factory():
    clients = []

    async def _make(application) -> AsyncClient:
        client = AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        )
        await client.__aenter__()
        clients.append(client)
        return client

    yield _make

    for client in reversed(clients):
        await client.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def app(app_factory):
    return await app_factory()


@pytest_asyncio.fixture
async def client(app, client_factory):
    return await client_factory(app)


@pytest_asyncio.fixture
async def api(app_factory, client_factory):
    """`app, client = await api(glm_api_key="test-key")` —— 按用例定制配置。"""

    async def _make(**overrides):
        application = await app_factory(**overrides)
        client = await client_factory(application)
        return application, client

    return _make


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


def install_provider(application, fake: FakeProvider) -> FakeProvider:
    application.state.ai_gateway.router.provider = fake
    application.state.provider = fake
    return fake


__all__ = [
    "FakeProvider",
    "ProviderError",
    "install_provider",
    "pytest",
    "pytest_asyncio",
]

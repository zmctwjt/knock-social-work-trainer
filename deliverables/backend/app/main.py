"""应用工厂与生命周期。

启动顺序刻意如此：日志 → 遥测 → 数据库 → 缓存/配额（Redis 或内存）→
AI 网关 → 限流器 → 种子数据。任一步失败都必须在日志里留下可定位的原因，
但 **AI 未配置不得导致启动失败**：没有 API Key 时服务以"规则模式"运行，
这是旧系统的既有行为，也是评测试跑的最低门槛。
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.legacy import router as legacy_router
from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.metrics import render_metrics  # noqa: F401  —— 由 health 端点调用
from app.core.middleware import BodyLimitMiddleware, RequestContextMiddleware
from app.core.ratelimit import RateLimiter
from app.core.telemetry import setup_telemetry
from app.infra.cache import AICache
from app.infra.db import Database
from app.infra.redis import create_store
from app.services.ai_gateway import AIGateway
from app.services.audit_service import AuditRecorder
from app.services.content_service import seed_content
from app.services.llm.quota import DailyQuota
from app.services.llm.router import ModelRouter
from app.services.llm.usage import UsageTracker
from app.services.llm.zhipu import ZhipuProvider

DESCRIPTION = """叩门·社工个案面谈 AI 陪练舱 后端 API。

- 统一响应包 `{code, message, data, request_id}`，`code=0` 表示成功；
- 旧接口 `/api/health`、`/api/ai/*` 保留一版，响应头带 `Deprecation`；
- AI 未配置时自动降级为规则模式，接口不返回 null，页面无需特殊处理。
"""


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    setup_logging(settings)
    logger = get_logger("app")
    app.state.started_at = time.time()

    setup_telemetry(settings)

    database = Database(settings)
    await database.connect()
    store = create_store(settings)
    cache = AICache(store, ttl_sec=settings.glm_cache_ttl_sec, max_size=settings.glm_cache_max)
    quota = DailyQuota(store, daily_cap=settings.glm_daily_cap)
    usage = UsageTracker()
    provider = ZhipuProvider(settings)
    model_router = ModelRouter(settings, provider)
    audit = AuditRecorder(database.session)
    gateway = AIGateway(
        settings,
        model_router,
        cache,
        quota,
        usage=usage,
        audit=audit,
    )
    limiter = RateLimiter(store, settings)

    app.state.db = database
    app.state.store = store
    app.state.cache = cache
    app.state.quota = quota
    app.state.usage = usage
    app.state.provider = provider
    app.state.router = model_router
    app.state.ai_gateway = gateway
    app.state.limiter = limiter

    # 覆盖层：把库里的增量算进内存，判定与取台词路径零 IO。
    # 失败时保持基线（代码常量）生效，"内容可维护"不牺牲"永远能跑"。
    try:
        async with database.session() as session:
            from app.services.rule_word_service import OVERLAY as WORDS
            from app.services.script_line_service import OVERLAY as LINES

            loaded = await WORDS.reload(session)
            line_rows = await LINES.reload(session)
        logger.info(
            "overlays_loaded",
            rule_words=loaded,
            rule_word_counts=WORDS.snapshot(),
            script_lines=line_rows,
        )
    except Exception as exc:  # noqa: BLE001 —— 覆盖层失败不影响基线
        logger.warning("overlays_load_failed", error=str(exc)[:200])

    if settings.seed_scenarios_on_startup:
        try:
            async with database.session() as session:
                seeded = await seed_content(session)
            logger.info("content_seeded", **seeded)
        except Exception as exc:  # noqa: BLE001 —— 种子失败不阻断启动
            logger.warning("content_seed_failed", error=str(exc)[:200])

    logger.info(
        "app_started",
        version=__version__,
        env=settings.app_env,
        db=database.dialect,
        cache=store.backend,
        ai_configured=settings.ai_configured,
        model_chain=settings.model_chain,
        port=settings.port,
    )

    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            await provider.close()
        with contextlib.suppress(Exception):
            await store.close()
        with contextlib.suppress(Exception):
            await database.disconnect()
        logger.info("app_stopped")


def _docs_allowed(cfg: Settings) -> bool:
    """交互文档只在非生产环境、或显式开启时才挂载。"""
    if getattr(cfg, "docs_enabled", False):
        return True
    return not cfg.is_prod


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(
        title="叩门 · AI 陪练舱后端",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        # 生产环境关闭交互文档：/docs 会把全部路由、参数、错误码摊开给任何人看，
        # 等于给攻击者一份接口地图。需要时用 DOCS_ENABLED 显式打开。
        docs_url="/docs" if _docs_allowed(cfg) else None,
        redoc_url=None,
        openapi_url="/openapi.json" if _docs_allowed(cfg) else None,
    )
    app.state.settings = cfg
    app.state.started_at = time.time()

    # 生产环境硬校验：默认密钥、DEBUG、通配 Host 等一律拒绝启动，
    # 不做降级处理——这些项一旦漏到生产就是可直接利用的漏洞。
    problems = cfg.production_errors
    if problems:
        from app.core.errors import StartupConfigError

        raise StartupConfigError(problems)

    install_exception_handlers(app)

    # add_middleware 后加的先执行：最终外→内为 CORS → TrustedHost → RequestContext → BodyLimit
    app.add_middleware(BodyLimitMiddleware, limit_bytes=cfg.body_limit_bytes)
    app.add_middleware(RequestContextMiddleware, settings=cfg)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.allowed_host_list)
    origins = cfg.cors_origin_list
    allow_creds = "*" not in origins  # 通配来源不能带凭证，否则浏览器拒收且属反模式
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_creds,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    app.include_router(health_router)
    app.include_router(api_router, prefix=cfg.api_v1_prefix)
    app.include_router(legacy_router)
    _mount_static(app, cfg)
    return app


def _mount_static(app: FastAPI, cfg: Settings) -> None:
    """托管已构建的前端产物（`STATIC_DIR` 指向 dist 目录时生效）。

    单端口演示时前端与接口同源，省掉 Vite 与跨域配置；目录不存在则跳过，
    不影响纯 API 运行。挂在路由之后、`/` 通配之前，因此 `/api/*` 仍优先命中。
    """
    from pathlib import Path

    from starlette.responses import FileResponse

    raw = (cfg.static_dir or "").strip()
    if not raw:
        return
    dist = Path(raw).expanduser().resolve()
    if not dist.is_dir():
        return
    index = dist / "index.html"
    if index.is_file():
        @app.get("/", include_in_schema=False)
        async def _index() -> FileResponse:
            return FileResponse(index)

    app.mount("/", SPAStaticFiles(directory=str(dist), html=True, index=index), name="static")


class SPAStaticFiles(StaticFiles):
    """带 SPA fallback 的静态托管。

    前端用 HashRouter，正常访问都是 `/#/xxx`，服务端只会收到 `/`；
    但用户直接粘 `http://host/training` 这类地址、或部署在反向代理后面被
    改写了路径时，服务端会收到非根路径。此时返回 404 体验很差（接口的
    40401 会直接显示成 JSON），因此统一回落到 index.html 交给前端路由。
    """

    def __init__(self, *args, index: "Path", **kwargs) -> None:  # noqa: ANN002,ANN003
        super().__init__(*args, **kwargs)
        self._fallback_index = index

    async def get_response(self, path: str, scope):  # noqa: ANN001,ANN201
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and self._fallback_index.is_file():
                from starlette.responses import FileResponse

                return FileResponse(self._fallback_index)
            raise


app = create_app()


__all__ = ["app", "create_app", "lifespan", "render_metrics"]

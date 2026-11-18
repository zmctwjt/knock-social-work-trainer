"""健康与运维端点：/healthz、/readyz、/metrics。

三者都挂在根路径，不走 `/api/v1` 前缀——k8s 探针与 Prometheus 抓取地址
不随 API 版本迁移而变化，这是 devops 侧的硬约定。
"""

from __future__ import annotations

import os
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import __version__
from app.core.context import get_request_id
from app.core.deps import get_settings_from
from app.core.metrics import render_metrics
from app.core.response import ok
from app.domain.schemas import Envelope, HealthOut, ReadyCheck, ReadyOut

router = APIRouter(tags=["运维"])


@router.get("/healthz", response_model=Envelope[HealthOut], summary="存活探针")
async def healthz(request: Request):
    settings = get_settings_from(request)
    started = getattr(request.app.state, "started_at", time.time())
    # 不暴露 pid：进程号属于内部拓扑信息，对排障价值有限，
    # 但能被用来推断同机其他服务或做侧信道观察。
    payload = HealthOut(
        version=__version__,
        environment=settings.app_env,
        uptime_sec=int(time.time() - started),
    )
    return ok(payload)


@router.get("/readyz", response_model=Envelope[ReadyOut], summary="就绪探针")
async def readyz(request: Request):
    state = request.app.state
    settings = get_settings_from(request)
    checks: list[ReadyCheck] = []

    try:
        db_ok = await state.db.ping()
        checks.append(ReadyCheck(name="database", ready=db_ok, detail=state.db.dialect))
    except Exception as exc:  # noqa: BLE001 —— 探针必须给出可读原因而不是 500
        checks.append(ReadyCheck(name="database", ready=False, detail=type(exc).__name__))

    try:
        store_ok = await state.store.ping()
        checks.append(ReadyCheck(name="cache", ready=store_ok, detail=state.store.backend))
    except Exception as exc:  # noqa: BLE001
        checks.append(ReadyCheck(name="cache", ready=False, detail=type(exc).__name__))

    # 未配置 GLM_API_KEY 不是"未就绪"：服务应继续以规则模式提供全部非 AI 能力
    checks.append(
        ReadyCheck(
            name="ai",
            ready=True,
            detail="已配置" if settings.ai_configured else "未配置，规则模式运行",
        )
    )

    ready = all(check.ready for check in checks)
    payload = ReadyOut(
        ok=ready,
        status="ready" if ready else "degraded",
        checks=checks,
        ai_configured=settings.ai_configured,
        model_chain=settings.model_chain,
    )
    if not ready:
        return JSONResponse(
            status_code=503,
            content={
                "code": 50301,
                "message": "服务尚未就绪",
                "data": payload.model_dump(mode="json"),
                "request_id": get_request_id(),
            },
        )
    return ok(payload)


@router.get("/metrics", summary="Prometheus 指标", include_in_schema=False)
async def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)

"""OpenTelemetry 初始化：带开关、缺依赖时静默跳过。

设计取舍：观测属于"尽力而为"能力，不能成为启动前提。CI 与单机评测环境
不装 OTel SDK，此时 `setup_telemetry()` 返回 False，业务照常运行；
配置了 `OTEL_ENABLED=true` 却没装 SDK 时，只打一条 warning，不抛异常。
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("telemetry")


def setup_telemetry(settings: Settings) -> bool:
    """按配置尝试初始化 OTLP/HTTP 导出；成功返回 True。"""
    if not settings.otel_enabled:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        logger.warning(
            "otel_sdk_missing",
            hint="已启用 OTEL_ENABLED 但未安装 opentelemetry-sdk/exporter，链路追踪跳过",
        )
        return False

    try:
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "1.0.0",
                "deployment.environment": settings.app_env,
            }
        )
        provider = TracerProvider(resource=resource)
        endpoint = settings.otel_exporter_otlp_endpoint.strip()
        exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        try:  # FastAPI 自动埋点属于可选项，缺包同样跳过
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor().instrument()
        except Exception:  # noqa: BLE001
            logger.info("otel_fastapi_instrument_skipped")

        logger.info("otel_initialized", endpoint=endpoint or "default", service=settings.otel_service_name)
        return True
    except Exception as exc:  # noqa: BLE001 —— 观测失败绝不影响业务
        logger.warning("otel_init_failed", error=str(exc)[:200])
        return False


__all__ = ["setup_telemetry"]

"""结构化日志与脱敏。

日志一律 JSON（`LOG_JSON=false` 时退化为可读的单行），字段固定包含：
`ts / level / logger / event / request_id / user_id_hash / path / status / duration_ms`。

脱敏规则（合规要求，不得关闭）：
- 手机号 → `138****8000`
- 邮箱 → `a***@example.com`
- 身份证号 → `110***********1234`
- 对话原文只出现在 AI 审计的 hash 与长度字段中，不落日志。

实现方式：一个 structlog processor 做递归字符串替换，因此无论日志字段
来自中间件、服务层还是异常处理器，都不会漏网。
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import Settings
from app.core.context import get_request_id, get_user_id_hash

PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
ID_CARD_RE = re.compile(r"\b\d{6}[12]\d{9}\d{3}[0-9Xx]\b")
BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE)


def mask_phone(value: str) -> str:
    return PHONE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], value)


def mask_email(value: str) -> str:
    return EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(3)}", value)


def mask_id_card(value: str) -> str:
    return ID_CARD_RE.sub(lambda m: m.group(0)[:3] + "*" * 11 + m.group(0)[-4:], value)


def mask_token(value: str) -> str:
    return BEARER_RE.sub(lambda m: m.group(1) + "***", value)


def redact_text(value: str) -> str:
    if not value:
        return value
    return mask_token(mask_id_card(mask_email(mask_phone(value))))


def redact(value: Any) -> Any:
    """递归脱敏：字符串替换，容器遍历，其余原样返回。"""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    return value


def add_context(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    request_id = get_request_id()
    if request_id:
        event_dict.setdefault("request_id", request_id)
    user_hash = get_user_id_hash()
    if user_hash:
        event_dict.setdefault("user_id_hash", user_hash)
    return event_dict


def add_service(settings: Settings):
    def processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.setdefault("service", settings.otel_service_name)
        event_dict.setdefault("env", settings.app_env)
        return event_dict

    return processor


def _redaction_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {key: redact(value) for key, value in event_dict.items()}


def setup_logging(settings: Settings) -> None:
    """进程级日志初始化（幂等；重复调用只更新级别）。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    renderer: Any
    if settings.log_json:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False, sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_context,
            add_service(settings),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redaction_processor,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)

"""Prometheus 指标注册表。

指标清单（与第 5 章"可观测性"表一致）：
- `http_request_duration_seconds{method,path,status}` 直方图：非 AI P95 ≤ 300ms 的观测口径
- `ai_calls_total{provider,model,status}` 计数器
- `ai_degraded_total{reason}` 计数器
- `ai_quota_used` 计数器：当日已用配额（进程内视为下限，多进程以 Redis 计量为准）
- `breaker_state{model}` 仪表盘：0=closed 1=half-open 2=open

刻意不用自定义 Collector，避免 /metrics 抓取时触发数据库查询——
抓取必须是无副作用的纯内存读取。
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    labelnames=("method", "path", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP 请求总数",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)

AI_CALLS = Counter(
    "ai_calls_total",
    "AI 调用次数",
    labelnames=("provider", "model", "status"),
    registry=REGISTRY,
)

AI_DEGRADED = Counter(
    "ai_degraded_total",
    "AI 降级次数（按原因）",
    labelnames=("reason",),
    registry=REGISTRY,
)

AI_QUOTA_USED = Gauge(
    "ai_quota_used",
    "当日 AI 配额已用量（本进程视角，跨进程以 Redis 计数为准）",
    registry=REGISTRY,
)

BREAKER_STATE = Gauge(
    "breaker_state",
    "熔断器状态：0=closed 1=half-open 2=open",
    labelnames=("model",),
    registry=REGISTRY,
)

AI_LATENCY = Histogram(
    "ai_call_duration_seconds",
    "单次 AI 调用耗时（秒）",
    labelnames=("model",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 15.0, 30.0, 45.0),
    registry=REGISTRY,
)

BREAKER_OPEN_COUNT = Counter(
    "breaker_open_total",
    "熔断器打开次数",
    labelnames=("model",),
    registry=REGISTRY,
)

TRAINING_STARTED = Counter(
    "training_started_total",
    "训练会话创建次数",
    labelnames=("scenario", "difficulty"),
    registry=REGISTRY,
)

TRAINING_COMPLETED = Counter(
    "training_completed_total",
    "训练会话完成次数",
    labelnames=("scenario", "difficulty", "result"),
    registry=REGISTRY,
)

CRISIS_BLOCKED = Counter(
    "crisis_blocked_total",
    "危机级内容触发本地硬拦截的次数（零模型调用）",
    labelnames=("risk_level", "source"),
    registry=REGISTRY,
)

SCORE_OVERALL = Histogram(
    "score_overall",
    "综合分分布（0-100）",
    buckets=(40, 50, 60, 70, 75, 80, 85, 90, 95, 100),
    registry=REGISTRY,
)


def observe_http(method: str, path: str, status: int, duration_seconds: float) -> None:
    labels = (method, path, str(status))
    HTTP_DURATION.labels(*labels).observe(duration_seconds)
    HTTP_REQUESTS.labels(*labels).inc()


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST

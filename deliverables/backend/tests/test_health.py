"""健康检查与运维端点。"""

from __future__ import annotations


async def test_healthz_ok(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"]
    assert body["request_id"]
    assert body["data"]["ok"] is True
    assert body["data"]["version"] == "1.0.0"
    assert body["data"]["environment"] == "test"


async def test_healthz_echoes_request_id(client):
    response = await client.get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"
    assert response.json()["request_id"] == "trace-abc-123"


async def test_readyz_reports_each_dependency(client):
    response = await client.get("/readyz")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is True
    names = {item["name"] for item in data["checks"]}
    assert {"database", "cache"} <= names
    # 不写死具体型号：模型链是可配置的（GLM_MODEL / GLM_FALLBACK_MODELS），
    # 断言"链首等于当前配置"才不会在换模型时误报。
    from app.core.config import get_settings

    assert data["model_chain"][0] == get_settings().glm_model
    assert len(data["model_chain"]) >= 1


async def test_metrics_exposes_prometheus_text(client):
    await client.get("/healthz")
    response = await client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers["content-type"]
    assert "openmetrics" in content_type or "text/plain" in content_type
    text = response.text
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text
    assert "ai_calls_total" in text
    assert "breaker_state" in text
    assert "training_started_total" in text
    assert "score_overall" in text


async def test_unknown_route_returns_envelope_404(client):
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 40401
    assert body["data"] is None

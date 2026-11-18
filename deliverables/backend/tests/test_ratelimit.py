"""限流与配额：单 IP 窗口限流、AI 日配额。"""

from __future__ import annotations


async def test_ai_endpoint_rate_limited(api):
    _application, client = await api(rate_limit_enabled=True, glm_rpm_per_ip=2)

    for _ in range(2):
        response = await client.post("/api/v1/ai/intent", json={"input": "今天有点累"})
        assert response.status_code == 200

    blocked = await client.post("/api/v1/ai/intent", json={"input": "今天有点烦"})
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == 42901
    assert "Retry-After" in blocked.headers


async def test_rate_limit_isolated_per_ip(api):
    _application, client = await api(rate_limit_enabled=True, glm_rpm_per_ip=1)

    first = await client.post(
        "/api/v1/ai/intent",
        json={"input": "今天有点累"},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert first.status_code == 200

    other = await client.post(
        "/api/v1/ai/intent",
        json={"input": "今天有点累"},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert other.status_code == 200


async def test_auth_endpoint_rate_limited(api):
    _application, client = await api(rate_limit_enabled=True, glm_rpm_per_ip=2)
    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "wrong-pass"}
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "wrong-pass"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == 42901


async def test_health_endpoints_are_not_rate_limited(api):
    _application, client = await api(rate_limit_enabled=True, glm_rpm_per_ip=1)
    for _ in range(5):
        response = await client.get("/healthz")
        assert response.status_code == 200

"""旧接口兼容层：响应形状、弃用头、危机铁律、无 key 不报 500。"""

from __future__ import annotations


async def test_legacy_health_shape(api):
    _application, client = await api()
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert set(body["ai"]) >= {"configured", "model", "fallback", "thinking", "timeoutMs"}
    assert body["ai"]["thinking"] == "disabled"
    assert body["ai"]["timeoutMs"] == 45000
    assert body["usage"]["dailyCap"] == 800
    assert body["usage"]["rpmPerIp"] == 20
    assert body["usage"]["concurrency"] == 2
    assert body["server"]["port"] == 8000


async def test_legacy_responses_are_marked_deprecated(api):
    _application, client = await api()
    response = await client.get("/api/usage")
    assert response.status_code == 200
    assert "deprecation" in response.headers
    assert response.headers["x-knock-api"] == "legacy"
    assert "/api/v1/" in response.headers["link"]


async def test_legacy_intent_success(api):
    application, client = await api(glm_api_key="test-key")
    from tests.conftest import FakeProvider, install_provider

    install_provider(application, FakeProvider(['{"intent":"共情"}']))
    response = await client.post(
        "/api/ai/intent", json={"input": "我最近总失眠", "stage": "第 1 阶段"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["intent"] == "共情"
    assert body["usedAI"] is True
    assert "ms" in body


async def test_legacy_crisis_intent_never_calls_model(api):
    application, client = await api(glm_api_key="test-key")
    from tests.conftest import FakeProvider, install_provider

    fake = install_provider(application, FakeProvider())
    response = await client.post("/api/ai/intent", json={"input": "我不想活了"})
    body = response.json()
    assert body["intent"] == "危机"
    assert body["usedAI"] is False
    assert body["degradeReason"] == "crisis_blocked"
    assert fake.calls == []


async def test_legacy_score_shape_is_camel_free(api):
    import json

    application, client = await api(glm_api_key="test-key")
    from tests.conftest import FakeProvider, install_provider

    scores = {
        key: {"score": 78, "reason": "稳定"}
        for key in ("empathy", "question", "advice", "ethics", "process", "risk")
    }
    install_provider(application, FakeProvider([json.dumps(scores, ensure_ascii=False)]))
    response = await client.post(
        "/api/ai/score",
        json={
            "dialogue": "学生：你最近睡得好吗？\n对象：总是半夜醒。",
            "stats": {"workerTurns": 1},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["usedAI"] is True
    assert set(body["scores"]) == {
        "empathy",
        "question",
        "advice",
        "ethics",
        "process",
        "risk",
    }
    for item in body["scores"].values():
        assert 0 <= item["score"] <= 100
        assert "reason" in item


async def test_legacy_score_without_key_reports_failure(api):
    """旧契约里 AI 不可用时 ok=false，由前端用本地规则分兜底。"""
    _application, client = await api(glm_api_key="")
    response = await client.post(
        "/api/ai/score", json={"dialogue": "学生：你最近怎么样？\n对象：还行。"}
    )
    body = response.json()
    assert body["ok"] is False
    assert body["usedAI"] is False
    assert body["scores"] is None


async def test_legacy_debrief_uses_next_step(api):
    application, client = await api(glm_api_key="")
    response = await client.post(
        "/api/ai/debrief",
        json={
            "scores": {
                "empathy": 55,
                "question": 48,
                "advice": 60,
                "ethics": 70,
                "process": 40,
                "risk": 65,
            }
        },
    )
    body = response.json()
    # 无 API key 时旧链路返回失败，由前端回落到本地模板（原 Node 行为）
    assert body["ok"] is False
    assert body["usedAI"] is False
    assert body["report"] is None and body["model"] is None


async def test_legacy_invalid_body_is_not_500(api):
    _application, client = await api()
    response = await client.post("/api/ai/score", content=b"not-json")
    assert response.status_code == 400
    body = response.json()
    # 参数解析失败统一走 40001 错误包，不返回 500
    assert body["code"] == 40001

"""AI 网关行为：成功、降级、危机硬拦截、配额。

只替换 LLMProvider，其余（缓存、配额、解析、审计）都走真实链路。
"""

from __future__ import annotations

import json

from tests.conftest import FakeProvider, ProviderError, install_provider


async def _ready(api, **overrides):
    settings = {"glm_api_key": "test-key", "rate_limit_enabled": False, **overrides}
    application, client = await api(**settings)
    return application, client


def _score_payload(score: int = 80) -> str:
    return json.dumps(
        {
            key: {"score": score, "reason": f"{key} 的表现"}
            for key in ("empathy", "question", "advice", "ethics", "process", "risk")
        },
        ensure_ascii=False,
    )


async def test_intent_uses_ai_and_records_meta(api):
    application, client = await _ready(api)
    fake = install_provider(application, FakeProvider(['{"intent":"共情"}']))
    response = await client.post("/api/v1/ai/intent", json={"input": "我最近总失眠"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] == "共情"
    assert data["source"] == "ai"
    assert data["meta"]["used_ai"] is True
    assert len(fake.calls) == 1


async def test_intent_crisis_never_calls_model(api):
    application, client = await _ready(api)
    fake = install_provider(application, FakeProvider())
    response = await client.post("/api/v1/ai/intent", json={"input": "我想死，活着没意思"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] == "危机"
    assert data["meta"]["used_ai"] is False
    assert data["meta"]["degrade_reason"] == "crisis_blocked"
    assert fake.calls == []


async def test_intent_without_api_key_degrades_to_rules(api):
    _application, client = await api(glm_api_key="")
    response = await client.post("/api/v1/ai/intent", json={"input": "你怎么看这件事？"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["meta"]["used_ai"] is False
    assert data["source"] == "rule"
    assert data["intent"] == "开放提问"


async def test_persona_returns_model_text(api):
    application, client = await _ready(api)
    fake = install_provider(application, FakeProvider(["你来了啊，快坐下吧。"]))
    response = await client.post(
        "/api/v1/ai/persona",
        json={
            "scenario_id": "W-01",
            "emotion": 45,
            "history": [{"role": "worker", "text": "王阿姨好"}],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["text"] == "你来了啊，快坐下吧。"
    assert data["meta"]["used_ai"] is True
    assert len(fake.calls) == 1


async def test_persona_timeout_falls_back_to_voice_line(api):
    application, client = await _ready(api)
    install_provider(
        application,
        FakeProvider(errors=[ProviderError.timeout() for _ in range(4)]),
    )
    response = await client.post(
        "/api/v1/ai/persona", json={"scenario_id": "W-01", "emotion": 20}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["meta"]["used_ai"] is False
    assert data["meta"]["degrade_reason"] == "timeout"
    assert data["text"]


async def test_score_merges_rule_and_ai(api):
    application, client = await _ready(api)
    install_provider(application, FakeProvider([_score_payload(80)]))
    response = await client.post(
        "/api/v1/ai/score",
        json={
            "dialogue": [
                {"role": "worker", "text": "你最近睡得好吗？"},
                {"role": "client", "text": "总是半夜醒。"},
                {"role": "worker", "text": "半夜醒来的时候，心里在想什么？"},
            ],
            "stage_index": 1,
            "total_stages": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["used_ai"] is True
    assert data["source"] == "blend"
    assert set(data["scores"]) == {
        "empathy",
        "question",
        "advice",
        "ethics",
        "process",
        "risk",
    }
    assert 0 <= data["total"] <= 100


async def test_score_non_json_degrades_to_rules(api):
    application, client = await _ready(api)
    install_provider(application, FakeProvider(["抱歉，我无法输出 JSON。"]))
    response = await client.post(
        "/api/v1/ai/score",
        json={"dialogue": [{"role": "worker", "text": "你最近怎么样？"}]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["used_ai"] is False
    assert data["source"] == "rule"
    assert data["missing"]


async def test_score_crisis_dialogue_skips_model(api):
    application, client = await _ready(api)
    fake = install_provider(application, FakeProvider())
    response = await client.post(
        "/api/v1/ai/score",
        json={
            "dialogue": [
                {"role": "client", "text": "我不想活了"},
                {"role": "worker", "text": "你现在安全吗？"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["used_ai"] is False
    assert data["meta"]["degrade_reason"] == "crisis_blocked"
    assert fake.calls == []


async def test_quota_exhausted_returns_42902(api):
    application, client = await _ready(api, glm_daily_cap=1)
    install_provider(application, FakeProvider(['{"intent":"共情"}']))

    first = await client.post("/api/v1/ai/intent", json={"input": "我最近有点累"})
    assert first.status_code == 200
    second = await client.post("/api/v1/ai/intent", json={"input": "今天有点烦"})
    assert second.status_code == 429
    assert second.json()["code"] == 42902


async def test_debrief_success(api):
    application, client = await _ready(api)
    payload = json.dumps(
        {
            "strength": "你在她描述失眠时选择了追问而不是给建议",
            "improvement": "结尾缺少总结确认，服务对象不知道下一步做什么",
            "nextStep": "下次练习时先用一句话复述对方的核心诉求，再进入下一阶段",
        },
        ensure_ascii=False,
    )
    install_provider(application, FakeProvider([payload]))
    response = await client.post(
        "/api/v1/ai/debrief",
        json={"scores": {"empathy": 80, "question": 60}, "nickname": "学员一"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["meta"]["used_ai"] is True
    assert data["next_step"]


async def test_debrief_falls_back_to_template(api):
    application, client = await _ready(api)
    install_provider(application, FakeProvider(errors=[ProviderError.server_error(500)]))
    response = await client.post(
        "/api/v1/ai/debrief",
        json={
            "scores": {
                "empathy": 50,
                "question": 45,
                "advice": 60,
                "ethics": 70,
                "process": 40,
                "risk": 75,
            }
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["meta"]["used_ai"] is False
    assert data["strength"] and data["improvement"] and data["next_step"]

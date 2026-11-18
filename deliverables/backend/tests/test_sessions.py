"""会话主流程：创建、发言、危机暂停、评分、结束、复盘、越权。"""

from __future__ import annotations

import json
import uuid

from tests.conftest import FakeProvider, install_provider
from tests.helpers import auth, create_session, login, seed_account, submit_turn

SIX = ("empathy", "question", "advice", "ethics", "process", "risk")


async def _student(application, client, username="stu1"):
    await seed_account(application, username=username)
    data = await login(client, username)
    return auth(data["tokens"]["access_token"]), data


async def test_create_and_list_session(api):
    application, client = await api()
    headers, _ = await _student(application, client)

    session = await create_session(client, headers)
    assert session["scenario_id"] == "W-01"
    assert session["status"] == "active"
    assert session["difficulty_label"] == "简单实习"
    assert session["turn_count"] == 0

    listed = await client.get("/api/v1/sessions", headers=headers)
    data = listed.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == session["id"]


async def test_create_session_is_idempotent(api):
    application, client = await api()
    headers, _ = await _student(application, client)

    first = await create_session(client, headers, client_session_id="cli-001")
    second = await create_session(client, headers, client_session_id="cli-001")
    assert first["id"] == second["id"]


async def test_submit_turn_returns_client_reply(api):
    application, client = await api(glm_api_key="test-key")
    headers, _ = await _student(application, client)
    install_provider(application, FakeProvider(['{"intent":"共情"}', "你来了啊，进来坐。"]))

    session = await create_session(client, headers)
    data = await submit_turn(client, headers, session["id"], "王阿姨，最近睡得好吗？")

    assert data["worker"]["speaker"] == "worker"
    assert data["worker"]["intent"] == "共情"
    assert data["client"]["speaker"] == "client"
    assert data["client"]["text"]
    assert data["paused"] is False
    assert data["session"]["turn_count"] == 1


async def test_submit_turn_replay_is_idempotent(api):
    application, client = await api(glm_api_key="test-key")
    headers, _ = await _student(application, client)
    fake = install_provider(application, FakeProvider(["第一句回应"]))
    session = await create_session(client, headers)

    first = await submit_turn(
        client, headers, session["id"], "你好", client_turn_id="turn-001"
    )
    second = await submit_turn(
        client, headers, session["id"], "你好", client_turn_id="turn-001"
    )
    assert first["worker"]["id"] == second["worker"]["id"]
    assert len(fake.calls) <= 2


async def test_crisis_turn_pauses_and_never_calls_model(api):
    application, client = await api(glm_api_key="test-key")
    headers, _ = await _student(application, client)
    fake = install_provider(application, FakeProvider())

    session = await create_session(client, headers)
    data = await submit_turn(client, headers, session["id"], "我想死，活着没意思")

    assert data["paused"] is True
    assert data["worker"]["intent"] == "危机"
    assert data["client"] is None
    assert data["session"]["crisis_flag"] is True
    assert fake.calls == []


async def test_score_stage_is_blended_and_repeatable(api):
    application, client = await api(glm_api_key="test-key")
    headers, _ = await _student(application, client)
    scores = {key: {"score": 82, "reason": "表现稳定"} for key in SIX}
    install_provider(application, FakeProvider([json.dumps(scores, ensure_ascii=False)]))
    session = await create_session(client, headers)
    await submit_turn(client, headers, session["id"], "王阿姨，最近睡得好吗？")

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/stages/1/score", headers=headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stage_index"] == 1
    assert data["source"] in ("blend", "rule")
    assert 0 <= data["total"] <= 100
    assert set(data["scores"]) == set(SIX)

    again = await client.post(
        f"/api/v1/sessions/{session['id']}/stages/1/score", headers=headers
    )
    assert again.json()["data"]["total"] == data["total"]


async def test_finish_and_debrief_flow(api):
    application, client = await api(glm_api_key="")
    headers, _ = await _student(application, client)
    session = await create_session(client, headers)

    finished = await client.post(
        f"/api/v1/sessions/{session['id']}/finish", headers=headers
    )
    assert finished.status_code == 200
    finish = finished.json()["data"]
    assert finish["session"]["status"] == "finished"
    assert finish["record_id"]

    debrief = await client.post(
        f"/api/v1/sessions/{session['id']}/debrief", headers=headers
    )
    assert debrief.status_code == 200
    report = debrief.json()["data"]
    assert report["strength"] and report["improvement"] and report["next_step"]
    assert report["used_ai"] is False

    replay = await client.post(
        f"/api/v1/sessions/{session['id']}/debrief", headers=headers
    )
    assert replay.json()["data"]["strength"] == report["strength"]


async def test_other_users_session_is_forbidden(api):
    application, client = await api()
    owner_headers, _ = await _student(application, client, "stu1")
    session = await create_session(client, owner_headers)

    other_headers, _ = await _student(application, client, "stu2")
    response = await client.get(
        f"/api/v1/sessions/{session['id']}", headers=other_headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == 40301

    missing = await client.get(
        f"/api/v1/sessions/{uuid.uuid4()}", headers=other_headers
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 40401


async def test_finished_session_rejects_new_turn(api):
    application, client = await api()
    headers, _ = await _student(application, client)
    session = await create_session(client, headers)
    await client.post(f"/api/v1/sessions/{session['id']}/finish", headers=headers)

    response = await client.post(
        f"/api/v1/sessions/{session['id']}/turns",
        json={"text": "再补一句"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == 40901

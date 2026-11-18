"""统计接口：个人汇总与热力图。"""

from __future__ import annotations

from tests.helpers import auth, create_session, login, seed_account


async def _student(application, client, username="stu1"):
    await seed_account(application, username=username)
    data = await login(client, username)
    return auth(data["tokens"]["access_token"])


async def _finished_sessions(client, headers, count=2):
    for _ in range(count):
        session = await create_session(client, headers)
        await client.post(f"/api/v1/sessions/{session['id']}/finish", headers=headers)


async def test_stats_me_aggregates_records(api):
    application, client = await api()
    headers = await _student(application, client)
    await _finished_sessions(client, headers, 2)

    response = await client.get("/api/v1/stats/me", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_sessions"] == 2
    assert data["active_days"] >= 1
    keys = {item["key"] for item in data["dimensions"]}
    assert keys == {"empathy", "question", "advice", "ethics", "process", "risk"}
    for item in data["dimensions"]:
        assert 0 <= item["average"] <= 100
        assert item["name"]
    assert len(data["recent"]) == 2


async def test_stats_heatmap_counts_today(api):
    application, client = await api()
    headers = await _student(application, client)
    await _finished_sessions(client, headers, 2)

    response = await client.get("/api/v1/stats/heatmap?days=7", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["days"]) == 7
    assert data["total"] == 2
    assert data["max_count"] == 2
    assert data["days"][-1]["count"] == 2
    assert data["days"][-1]["level"] >= 1


async def test_stats_requires_login(api):
    _application, client = await api()
    response = await client.get("/api/v1/stats/me")
    assert response.status_code == 401
    assert response.json()["code"] == 40101


async def test_heatmap_rejects_out_of_range_days(api):
    application, client = await api()
    headers = await _student(application, client)
    response = await client.get("/api/v1/stats/heatmap?days=999", headers=headers)
    assert response.status_code == 400
    assert response.json()["code"] == 40001

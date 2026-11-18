"""案例库与知识卡：种子数据、详情、404。"""

from __future__ import annotations


async def test_list_scenarios_returns_twelve_seeds(client):
    response = await client.get("/api/v1/scenarios")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 12
    assert len(data["items"]) == 12
    ids = {item["id"] for item in data["items"]}
    assert {"W-01", "C-03", "H-12"} <= ids
    first = next(item for item in data["items"] if item["id"] == "W-01")
    assert first["name"] == "王阿姨"
    assert first["difficulty_label"] == "简单实习"


async def test_scenario_detail_and_unknown_id(client):
    response = await client.get("/api/v1/scenarios/A-06")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == "A-06"
    assert data["sensitive_tag"]

    missing = await client.get("/api/v1/scenarios/X-99")
    assert missing.status_code == 404
    assert missing.json()["code"] == 40401


async def test_knowledge_cards_seeded_and_filterable(client):
    response = await client.get("/api/v1/knowledge/cards")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 19
    assert data["items"][0]["id"].startswith("T-")

    filtered = await client.get("/api/v1/knowledge/cards", params={"category": "共情"})
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] >= 1
    assert all(
        "共情" in item["category"] for item in filtered.json()["data"]["items"]
    )

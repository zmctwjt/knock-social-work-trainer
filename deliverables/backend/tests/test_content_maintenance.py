"""任务书缺口补齐测试：知识库关键词检索、台词节点维护。

对应毕业设计任务书"训练端-知识库：支持按案例与关键词检索"与
"管理端-内容维护：维护台词节点、技巧卡与判定词表"。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from app.services import session_service
from app.services.script_line_service import OVERLAY
from tests.helpers import auth, login, seed_account


async def _admin(application, client) -> dict[str, str]:
    await seed_account(application, username="root02", nickname="管理员", role=Role.ADMIN)
    token = (await login(client, "root02"))["tokens"]["access_token"]
    return auth(token)


# ── 知识库关键词检索 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_cards_keyword_search(api):
    application, client = await api()
    all_cards = (await client.get("/api/v1/knowledge/cards")).json()["data"]
    assert all_cards["total"] > 0

    # 取第一张卡的标题片段做关键词，应能搜到它
    title = all_cards["items"][0]["title"]
    fragment = title[:2]
    hit = (await client.get("/api/v1/knowledge/cards", params={"keyword": fragment})).json()
    assert hit["code"] == 0
    assert hit["data"]["total"] >= 1
    assert any(fragment in x["title"] for x in hit["data"]["items"])


@pytest.mark.asyncio
async def test_cards_keyword_no_match_returns_empty(api):
    _, client = await api()
    resp = await client.get("/api/v1/knowledge/cards", params={"keyword": "绝不存在的词xyz"})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_cards_category_and_keyword_combined(api):
    _, client = await api()
    resp = await client.get(
        "/api/v1/knowledge/cards", params={"category": "技巧", "keyword": "倾听"}
    )
    assert resp.status_code == 200
    for item in resp.json()["data"]["items"]:
        assert item["category"] == "技巧"


# ── 台词节点维护 ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_script_line_crud(api):
    application, client = await api()
    headers = await _admin(application, client)

    created = await client.post(
        "/api/v1/admin/script-lines",
        headers=headers,
        json={"text": "（沉默了很久）我不知道该怎么说。", "emotion_bucket": "low", "order_index": 1},
    )
    assert created.status_code == 200, created.text
    line_id = created.json()["data"]["id"]

    listed = (await client.get("/api/v1/admin/script-lines", headers=headers)).json()
    assert listed["code"] == 0
    assert any(x["id"] == line_id for x in listed["data"]["items"])
    assert [b["value"] for b in listed["data"]["buckets"]] == ["low", "mid", "high"]

    patched = await client.patch(
        f"/api/v1/admin/script-lines/{line_id}",
        headers=headers,
        json={"text": "（沉默许久）我……不知道从哪说起。", "active": True},
    )
    assert patched.status_code == 200
    assert "从哪说起" in patched.json()["data"]["text"]

    removed = await client.delete(f"/api/v1/admin/script-lines/{line_id}", headers=headers)
    assert removed.status_code == 200
    gone = await client.delete(f"/api/v1/admin/script-lines/{line_id}", headers=headers)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_script_line_rejects_bad_bucket(api):
    application, client = await api()
    headers = await _admin(application, client)
    resp = await client.post(
        "/api/v1/admin/script-lines",
        headers=headers,
        json={"text": "测试台词", "emotion_bucket": "extreme"},
    )
    # 项目统一用 40001 表达参数不合法（全局异常处理器把 422 归一成 400）
    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


@pytest.mark.asyncio
async def test_script_line_unknown_scenario_rejected(api):
    application, client = await api()
    headers = await _admin(application, client)
    resp = await client.post(
        "/api/v1/admin/script-lines",
        headers=headers,
        json={"text": "测试台词", "scenario_id": "Z-99"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_maintained_line_overrides_baseline(api):
    """新增台词后，同情绪档的取用应命中新台词而不是基线。"""
    application, client = await api()
    headers = await _admin(application, client)

    marker = "（低情绪自定义台词）我最近总是睡不好。"
    created = await client.post(
        "/api/v1/admin/script-lines",
        headers=headers,
        json={"text": marker, "emotion_bucket": "low", "order_index": 0},
    )
    assert created.status_code == 200

    # 低情绪（emotion<40）索引 0 → 应取到自定义台词
    picked = session_service._fallback_reply(20, 0, "W-01")
    assert picked == marker, f"应优先用维护的台词，实际 {picked!r}"

    # 未维护的高情绪档仍走基线
    baseline_high = session_service.FALLBACK_REPLIES["high"][0]
    assert session_service._fallback_reply(80, 0, "W-01") == baseline_high


@pytest.mark.asyncio
async def test_empty_overlay_falls_back_to_baseline(api):
    """覆盖层为空（如库故障）时必须回落到基线，对话不能中断。"""
    await api()  # 确保 app 起过一次、覆盖层已加载
    OVERLAY._by_key = {}
    baseline = session_service.FALLBACK_REPLIES["mid"][0]
    assert session_service._fallback_reply(50, 0, "W-01") == baseline


@pytest.mark.asyncio
async def test_student_cannot_manage_script_lines(api):
    application, client = await api()
    await seed_account(application, username="stu888", nickname="学员")
    token = (await login(client, "stu888"))["tokens"]["access_token"]

    for resp in (
        await client.get("/api/v1/admin/script-lines", headers=auth(token)),
        await client.post(
            "/api/v1/admin/script-lines", headers=auth(token), json={"text": "越权"}
        ),
    ):
        assert resp.status_code == 403
        assert resp.json()["code"] == 40301

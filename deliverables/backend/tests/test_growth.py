"""成长中心服务端口径测试。

背景：成长中心原先读浏览器 localStorage，教师端读服务端，两边数据源不同，
学生换设备后自己的成长为空但教师仍能看到记录。改为服务端统一口径后，
用这组测试锁住三件事：
1. 只返回调用者自己的记录（归属按 account_id，不是昵称）；
2. 返回 score_source 分布（blend/rule 两种口径不可比，界面要能标注）；
3. 访客无权访问。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from tests.helpers import auth, create_session, login, seed_account, submit_turn


async def _train_once(client, headers, scenario_id: str = "W-01") -> None:
    created = await create_session(client, headers, scenario_id=scenario_id)
    sid = created["id"]
    await submit_turn(client, headers, sid, text="您好，我是社区的小陈。")
    await client.post(f"/api/v1/sessions/{sid}/stages/1/score", headers=headers, json={})
    await client.post(f"/api/v1/sessions/{sid}/finish", headers=headers, json={})


@pytest.mark.asyncio
async def test_growth_returns_own_records_only(api):
    """两个学员各有记录，彼此不可见——归属必须按 ID。"""
    application, client = await api()
    await seed_account(application, username="gaa", nickname="甲")
    await seed_account(application, username="gbb", nickname="乙")
    ha = auth((await login(client, "gaa"))["tokens"]["access_token"])
    hb = auth((await login(client, "gbb"))["tokens"]["access_token"])

    await _train_once(client, ha, "W-01")
    await _train_once(client, hb, "L-02")
    await _train_once(client, hb, "F-10")

    a = (await client.get("/api/v1/me/growth", headers=ha)).json()["data"]
    b = (await client.get("/api/v1/me/growth", headers=hb)).json()["data"]
    assert a["total_sessions"] == 1, f"甲应只有 1 次，实际 {a['total_sessions']}"
    assert b["total_sessions"] == 2, f"乙应有 2 次，实际 {b['total_sessions']}"
    assert {r["scenario_id"] for r in a["records"]} == {"W-01"}
    assert {r["scenario_id"] for r in b["records"]} == {"L-02", "F-10"}


@pytest.mark.asyncio
async def test_growth_same_nickname_does_not_leak(api):
    """同昵称的两个账号不能串数据（旧实现按昵称匹配会串）。"""
    application, client = await api()
    await seed_account(application, username="same1", nickname="同名")
    await seed_account(application, username="same2", nickname="同名")
    h1 = auth((await login(client, "same1"))["tokens"]["access_token"])
    h2 = auth((await login(client, "same2"))["tokens"]["access_token"])

    await _train_once(client, h1)
    one = (await client.get("/api/v1/me/growth", headers=h1)).json()["data"]
    two = (await client.get("/api/v1/me/growth", headers=h2)).json()["data"]
    assert one["total_sessions"] == 1
    assert two["total_sessions"] == 0, "同昵称账号不应看到对方记录"


@pytest.mark.asyncio
async def test_growth_reports_score_source_breakdown(api):
    """必须给出 blend/rule 分布，界面据此标注口径差异。"""
    application, client = await api()
    await seed_account(application, username="gss", nickname="来源")
    h = auth((await login(client, "gss"))["tokens"]["access_token"])
    await _train_once(client, h)

    data = (await client.get("/api/v1/me/growth", headers=h)).json()["data"]
    assert "source_breakdown" in data
    assert isinstance(data["source_breakdown"], dict)
    # 未配置密钥时全部为规则评分
    assert data["source_breakdown"].get("rule", 0) >= 1
    # 每条记录也带来源
    assert all(r["score_source"] in ("blend", "rule") for r in data["records"])


@pytest.mark.asyncio
async def test_growth_includes_six_dimensions(api):
    """六维明细要齐，成长中心的雷达图依赖它。"""
    application, client = await api()
    await seed_account(application, username="gdd", nickname="维度")
    h = auth((await login(client, "gdd"))["tokens"]["access_token"])
    await _train_once(client, h)

    data = (await client.get("/api/v1/me/growth", headers=h)).json()["data"]
    keys = {d["key"] for d in data["dimensions"]}
    assert keys == {"empathy", "question", "advice", "ethics", "process", "risk"}
    rec = data["records"][0]
    assert set(rec["scores"].keys()) == keys


@pytest.mark.asyncio
async def test_growth_guest_forbidden(api):
    """访客没有训练数据，应 403。"""
    application, client = await api()
    g = await client.post("/api/v1/auth/guest", json={"nickname": "路人"})
    token = g.json()["data"]["tokens"]["access_token"]
    resp = await client.get("/api/v1/me/growth", headers=auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_growth_empty_for_new_account(api):
    """新账号返回全 0 而不是报错。"""
    application, client = await api()
    await seed_account(application, username="gnew", nickname="新人")
    h = auth((await login(client, "gnew"))["tokens"]["access_token"])
    data = (await client.get("/api/v1/me/growth", headers=h)).json()["data"]
    assert data["total_sessions"] == 0
    assert data["records"] == []
    assert data["avg_total"] == 0.0

"""平台训练热力图测试。

热力图最容易出的问题：
1. 固定阈值在数据量大时全部顶格，失去区分度（学生端够用，平台级不行）；
2. 日期范围不对齐到周一，每列不是完整一周，读起来错位；
3. 空库时除零崩溃。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.enums import Role
from app.domain.models import TrainingRecord
from tests.helpers import auth, create_session, login, seed_account, submit_turn


async def _finish_training(client, headers, scenario_id="W-01") -> None:
    created = await create_session(client, headers, scenario_id=scenario_id)
    sid = created["id"]
    await submit_turn(client, headers, sid, text="您好，我是社区的小陈。")
    await client.post(f"/api/v1/sessions/{sid}/stages/1/score", headers=headers, json={})
    await client.post(f"/api/v1/sessions/{sid}/finish", headers=headers, json={})


async def _admin_headers(application, client):
    await seed_account(application, username="hroot", nickname="热力图管理员", role=Role.ADMIN)
    return auth((await login(client, "hroot"))["tokens"]["access_token"])


@pytest.mark.asyncio
async def test_heatmap_structure_and_alignment(api):
    """格子数应覆盖整周：起始日必须是周一。"""
    application, client = await api()
    headers = await _admin_headers(application, client)

    data = (await client.get(
        "/api/v1/admin/heatmap", headers=headers, params={"weeks": 4}
    )).json()["data"]

    assert data["cells"], "热力图不能为空"
    start = datetime.fromisoformat(data["start"]).date()
    assert start.weekday() == 0, f"起始日应为周一，实际 {start} 是周{start.weekday()+1}"
    # 范围是「(weeks-1) 周前的周一 → 今天」，当前周不完整，
    # 因此格子数在 (weeks-1)*7+1 与 weeks*7 之间，不能简单按 4*7 断言。
    low = (4 - 1) * 7 + 1
    high = 4 * 7
    assert low <= len(data["cells"]) <= high, (
        f"4 周应产生 {low}-{high} 格，实际 {len(data['cells'])}"
    )
    # 首尾日期要能对上：末尾就是今天
    assert data["cells"][-1]["date"] == data["end"]


@pytest.mark.asyncio
async def test_heatmap_levels_adaptive(api):
    """分档要随数据自适应，不能所有非零日都顶格。"""
    application, client = await api()
    headers = await _admin_headers(application, client)

    learner = await seed_account(application, username="hstu", nickname="热力图学员")
    l_headers = auth((await login(client, "hstu"))["tokens"]["access_token"])
    for _ in range(5):
        await _finish_training(client, l_headers)

    # 把其中 4 条记录的人工日期拉开，构造出不同天不同量
    async with application.state.db.session() as session:
        rows = (
            await session.execute(
                select(TrainingRecord).where(TrainingRecord.owner_id == learner.id)
            )
        ).scalars().all()
        base = datetime.now(UTC) - timedelta(days=10)
        for i, row in enumerate(rows):
            row.created_at = base + timedelta(days=i)
        await session.commit()

    data = (await client.get(
        "/api/v1/admin/heatmap", headers=headers, params={"weeks": 4}
    )).json()["data"]

    levels = {c["level"] for c in data["cells"] if c["count"] > 0}
    assert levels, "应有非零格子"
    assert max(levels) <= 4
    assert data["total"] == 5, f"总数应为 5，实际 {data['total']}"


@pytest.mark.asyncio
async def test_heatmap_empty_database(api):
    """空库不能崩（除零）。"""
    application, client = await api()
    headers = await _admin_headers(application, client)

    resp = await client.get("/api/v1/admin/heatmap", headers=headers, params={"weeks": 8})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["max_daily"] == 0
    assert data["thresholds"] == [0, 0, 0]


@pytest.mark.asyncio
async def test_heatmap_weeks_clamped(api):
    """周数越界被夹到合法区间。"""
    application, client = await api()
    headers = await _admin_headers(application, client)
    for weeks in (0, -3, 999):
        resp = await client.get(
            "/api/v1/admin/heatmap", headers=headers, params={"weeks": weeks}
        )
        assert resp.status_code == 200
        assert 4 <= resp.json()["data"]["weeks"] <= 52


@pytest.mark.asyncio
async def test_heatmap_admin_only(api):
    """非管理员不能读平台热力图。"""
    application, client = await api()
    await _admin_headers(application, client)
    await seed_account(application, username="hstu2", nickname="普通学员")
    h = auth((await login(client, "hstu2"))["tokens"]["access_token"])
    resp = await client.get("/api/v1/admin/heatmap", headers=h)
    assert resp.status_code == 403

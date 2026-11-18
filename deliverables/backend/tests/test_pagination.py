"""分页接口测试。

分页最容易出三类错，这里逐一覆盖：
1. `total` 用了本页条数而非过滤后的总数（前端会算出错误页数）；
2. 页码越界返回 500 或空指针，而不是空列表；
3. 筛选变化后仍停留在旧页码，导致用户看到空列表。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from tests.helpers import auth, login, seed_account


async def _admin_headers(application, client) -> dict[str, str]:
    await seed_account(application, username="root03", nickname="管理员", role=Role.ADMIN)
    token = (await login(client, "root03"))["tokens"]["access_token"]
    return auth(token)


async def _make_students(application, n: int) -> None:
    for i in range(n):
        await seed_account(application, username=f"pg{i:03d}", nickname=f"分页学员{i}")


@pytest.mark.asyncio
async def test_accounts_pagination_metadata(api):
    """返回的 total 是过滤后总数，pages 按 page_size 正确向上取整。"""
    application, client = await api()
    headers = await _admin_headers(application, client)
    await _make_students(application, 7)

    body = (await client.get(
        "/api/v1/admin/accounts", headers=headers, params={"page": 1, "page_size": 3}
    )).json()
    data = body["data"]
    assert body["code"] == 0
    assert len(data["items"]) == 3, "第 1 页应返回 page_size 条"
    # 1 个管理员 + 7 个学员
    assert data["total"] == 8, f"total 应为过滤后总数 8，实际 {data['total']}"
    assert data["pages"] == 3, "8 条 / 每页 3 条 = 3 页"
    assert data["page"] == 1 and data["page_size"] == 3


@pytest.mark.asyncio
async def test_accounts_pagination_walks_all_pages(api):
    """逐页翻完应不重不漏。"""
    application, client = await api()
    headers = await _admin_headers(application, client)
    await _make_students(application, 7)

    seen: list[str] = []
    page = 1
    while True:
        data = (await client.get(
            "/api/v1/admin/accounts", headers=headers,
            params={"page": page, "page_size": 3},
        )).json()["data"]
        seen.extend(x["username"] for x in data["items"])
        if page >= data["pages"]:
            break
        page += 1

    assert len(seen) == len(set(seen)), "翻页出现重复条目"
    assert len(seen) == 8, f"翻完应拿到全部 8 条，实际 {len(seen)}"


@pytest.mark.asyncio
async def test_pagination_out_of_range_returns_empty(api):
    """页码超出范围返回空列表而非报错。"""
    application, client = await api()
    headers = await _admin_headers(application, client)

    resp = await client.get(
        "/api/v1/admin/accounts", headers=headers, params={"page": 999, "page_size": 10}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] >= 1, "总数仍应正确，便于前端显示‘共 N 条’"


@pytest.mark.asyncio
async def test_pagination_invalid_params_are_clamped(api):
    """非法分页参数被夹到合法区间，不抛 500。"""
    application, client = await api()
    headers = await _admin_headers(application, client)

    for params in (
        {"page": 0, "page_size": 10},
        {"page": -3, "page_size": 10},
        {"page": 1, "page_size": 0},
        {"page": 1, "page_size": 99999},
    ):
        resp = await client.get("/api/v1/admin/accounts", headers=headers, params=params)
        assert resp.status_code == 200, f"{params} 应被夹住而不是报错"
        data = resp.json()["data"]
        assert data["page"] >= 1
        assert 1 <= data["page_size"] <= 200


@pytest.mark.asyncio
async def test_pagination_with_role_filter(api):
    """筛选与分页组合：total 反映筛选后的数量。"""
    application, client = await api()
    headers = await _admin_headers(application, client)
    await _make_students(application, 5)
    await seed_account(application, username="tea_pg", nickname="分页教师", role=Role.TEACHER)

    data = (await client.get(
        "/api/v1/admin/accounts", headers=headers,
        params={"role": "student", "page": 1, "page_size": 2},
    )).json()["data"]
    assert data["total"] == 5, f"学生应为 5 人，实际 {data['total']}"
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_learner_records_paginated(api):
    """学员记录分页：结构与账号分页一致。"""
    application, client = await api()
    await seed_account(application, username="tea_rec", nickname="记录教师", role=Role.TEACHER)
    learner = await seed_account(application, username="stu_rec", nickname="记录学员")
    teacher = await seed_account(
        application, username="tea_rec2", nickname="记录教师2", role=Role.TEACHER
    )
    async with application.state.db.session() as session:
        me = await session.get(type(learner), learner.id)
        me.teacher_id = teacher.id
        await session.commit()

    token = (await login(client, "tea_rec2"))["tokens"]["access_token"]
    resp = await client.get(
        f"/api/v1/teacher/learners/{learner.id}/records",
        headers=auth(token),
        params={"page": 1, "page_size": 5},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {"items", "total", "page", "page_size", "pages"} <= set(data)


@pytest.mark.asyncio
async def test_learner_records_forbidden_returns_empty_not_error(api):
    """非名下学员：返回空集而非 403，避免通过状态码探测账号是否存在。"""
    application, client = await api()
    await seed_account(application, username="tea_x", nickname="外部教师", role=Role.TEACHER)
    outsider = await seed_account(application, username="stu_x", nickname="外部学员")

    token = (await login(client, "tea_x"))["tokens"]["access_token"]
    resp = await client.get(
        f"/api/v1/teacher/learners/{outsider.id}/records", headers=auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []

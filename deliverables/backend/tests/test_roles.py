"""多角色能力测试：教师端班级看板与学员隔离、管理员端账号/内容/系统管理。

对应用户手册与设计文档表 5-5 的角色权限矩阵，重点验证三件事：
1. 教师只能看名下学员，跨班返回空集而非报错；
2. 学生访问教师端 / 管理端一律 40301；
3. 管理员的停用账号立即生效（登录被拒）。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from tests.helpers import PASSWORD, auth, login, seed_account


async def _teacher_with_learner(application, client):
    """造一个教师 + 一名名下学员 + 一名无关学员。"""
    teacher = await seed_account(
        application, username="teach01", nickname="张老师", role=Role.TEACHER
    )
    mine = await seed_account(application, username="stu001", nickname="学员甲")
    other = await seed_account(application, username="stu002", nickname="学员乙")

    async with application.state.db.session() as session:
        me = await session.get(type(teacher), mine.id)
        me.teacher_id = teacher.id
        await session.commit()

    t_token = (await login(client, "teach01"))["tokens"]["access_token"]
    return teacher, mine, other, t_token


@pytest.mark.asyncio
async def test_teacher_sees_only_own_learners(api):
    application, client = await api()
    _, mine, _other, t_token = await _teacher_with_learner(application, client)

    body = (await client.get("/api/v1/teacher/learners", headers=auth(t_token))).json()
    assert body["code"] == 0
    names = [x["username"] for x in body["data"]["items"]]
    assert names == ["stu001"], f"教师不应看到非名下学员，实际 {names}"
    assert mine.username in names


@pytest.mark.asyncio
async def test_teacher_class_stats_shape(api):
    application, client = await api()
    _, _mine, _other, t_token = await _teacher_with_learner(application, client)

    body = (await client.get("/api/v1/teacher/stats", headers=auth(t_token))).json()
    assert body["code"] == 0
    data = body["data"]
    assert data["learners"] == 1
    assert data["sessions"] == 0
    assert set(data) >= {"learners", "sessions", "avg_total", "dimensions"}


@pytest.mark.asyncio
async def test_teacher_cross_class_records_returns_empty(api):
    """跨班查看他人记录：返回空集，不报错也不泄露（F12 验收项）。"""
    application, client = await api()
    _, _mine, other, t_token = await _teacher_with_learner(application, client)

    resp = await client.get(
        f"/api/v1/teacher/learners/{other.id}/records", headers=auth(t_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == []


@pytest.mark.asyncio
async def test_teacher_can_bind_learner(api):
    application, client = await api()
    _, _mine, other, t_token = await _teacher_with_learner(application, client)

    resp = await client.post(
        "/api/v1/teacher/learners", headers=auth(t_token), json={"username": other.username}
    )
    assert resp.status_code == 200 and resp.json()["code"] == 0
    again = (await client.get("/api/v1/teacher/learners", headers=auth(t_token))).json()
    assert {x["username"] for x in again["data"]["items"]} == {"stu001", "stu002"}


@pytest.mark.asyncio
async def test_student_forbidden_from_teacher_and_admin(api):
    application, client = await api()
    await seed_account(application, username="stu009", nickname="学员")
    s_token = (await login(client, "stu009"))["tokens"]["access_token"]

    for path in ("/api/v1/teacher/learners", "/api/v1/teacher/stats", "/api/v1/admin/overview",
                 "/api/v1/admin/accounts"):
        resp = await client.get(path, headers=auth(s_token))
        assert resp.status_code == 403, f"{path} 应为 403，实际 {resp.status_code}"
        assert resp.json()["code"] == 40301


@pytest.mark.asyncio
async def test_guest_forbidden_from_admin(api):
    application, client = await api()
    guest = (await client.post("/api/v1/auth/guest", json={"nickname": "路人"})).json()
    token = guest["data"]["tokens"]["access_token"]
    resp = await client.get("/api/v1/admin/overview", headers=auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_lists_and_creates_accounts(api):
    application, client = await api()
    await seed_account(application, username="root", nickname="管理员", role=Role.ADMIN)
    a_token = (await login(client, "root"))["tokens"]["access_token"]

    created = await client.post(
        "/api/v1/admin/accounts",
        headers=auth(a_token),
        json={"username": "t_new", "password": PASSWORD, "nickname": "新教师", "role": "teacher"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["role"] == "teacher"

    listed = (await client.get("/api/v1/admin/accounts", headers=auth(a_token))).json()
    assert listed["code"] == 0
    assert {"root", "t_new"} <= {x["username"] for x in listed["data"]["items"]}

    dup = await client.post(
        "/api/v1/admin/accounts",
        headers=auth(a_token),
        json={"username": "t_new", "password": PASSWORD},
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_admin_disable_account_blocks_login(api):
    application, client = await api()
    await seed_account(application, username="root", nickname="管理员", role=Role.ADMIN)
    target = await seed_account(application, username="s_dis", nickname="待停用")
    a_token = (await login(client, "root"))["tokens"]["access_token"]

    resp = await client.patch(
        f"/api/v1/admin/accounts/{target.id}/active",
        headers=auth(a_token),
        json={"active": False},
    )
    assert resp.status_code == 200 and resp.json()["data"]["is_active"] is False

    blocked = await client.post(
        "/api/v1/auth/login", json={"username": "s_dis", "password": PASSWORD}
    )
    # 停用账号走 403（账号存在但被禁用），与"凭证错误"的 401 区分，便于前端给出不同提示
    assert blocked.status_code == 403, f"停用后登录应被拒绝，实际 {blocked.status_code}"


@pytest.mark.asyncio
async def test_admin_upserts_and_archives_scenario(api):
    application, client = await api()
    await seed_account(application, username="root", nickname="管理员", role=Role.ADMIN)
    a_token = (await login(client, "root"))["tokens"]["access_token"]

    payload = {
        "id": "X-99",
        "name": "测试角色",
        "age": 40,
        "gender": "女",
        "archetype": "测试",
        "brief": "用于验证内容维护接口",
        "system_prompt": "你扮演一位测试角色，只用简短口语回应。",
    }
    made = await client.post("/api/v1/admin/scenarios", headers=auth(a_token), json=payload)
    assert made.status_code == 200, made.text
    assert made.json()["data"]["id"] == "X-99"

    listed = (await client.get("/api/v1/scenarios", headers=auth(a_token))).json()
    assert "X-99" in {x["id"] for x in listed["data"]["items"]}

    archived = await client.delete("/api/v1/admin/scenarios/X-99", headers=auth(a_token))
    assert archived.status_code == 200
    after = (await client.get("/api/v1/scenarios", headers=auth(a_token))).json()
    assert "X-99" not in {x["id"] for x in after["data"]["items"]}, "下架后不应出现在列表"


@pytest.mark.asyncio
async def test_admin_upserts_and_deletes_card(api):
    application, client = await api()
    await seed_account(application, username="root", nickname="管理员", role=Role.ADMIN)
    a_token = (await login(client, "root"))["tokens"]["access_token"]

    made = await client.post(
        "/api/v1/admin/cards",
        headers=auth(a_token),
        json={"id": "T-99", "title": "测试技巧", "category": "技巧", "summary": "摘要"},
    )
    assert made.status_code == 200, made.text

    updated = await client.post(
        "/api/v1/admin/cards",
        headers=auth(a_token),
        json={"id": "T-99", "title": "测试技巧（改）"},
    )
    assert updated.json()["data"]["title"] == "测试技巧（改）"

    removed = await client.delete("/api/v1/admin/cards/T-99", headers=auth(a_token))
    assert removed.status_code == 200
    gone = await client.delete("/api/v1/admin/cards/T-99", headers=auth(a_token))
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_admin_overview_and_ai_logs(api):
    application, client = await api()
    await seed_account(application, username="root", nickname="管理员", role=Role.ADMIN)
    a_token = (await login(client, "root"))["tokens"]["access_token"]

    overview = await client.get("/api/v1/admin/overview", headers=auth(a_token))
    assert overview.status_code == 200
    data = overview.json()["data"]
    assert data["accounts"] >= 1
    assert data["daily_cap"] > 0
    assert isinstance(data["model_chain"], list)

    logs = await client.get("/api/v1/admin/ai-logs", headers=auth(a_token))
    assert logs.status_code == 200 and logs.json()["code"] == 0


@pytest.mark.asyncio
async def test_admin_can_view_any_learner_via_teacher_endpoint(api):
    """管理员继承教师权限，可跨班查看。"""
    application, client = await api()
    _, _mine, other, _t = await _teacher_with_learner(application, client)
    await seed_account(application, username="root", nickname="管理员", role=Role.ADMIN)
    a_token = (await login(client, "root"))["tokens"]["access_token"]

    resp = await client.get(
        f"/api/v1/teacher/learners/{other.id}/records", headers=auth(a_token)
    )
    assert resp.status_code == 200

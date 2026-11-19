"""案例归属与教师端案例管理。

背景：原先只有管理员能在后台改案例，教师无法新增自己的服务对象。
开放教师建案例后，必须同时锁住三条边界，否则任何教师都能
改掉课程自带案例或别的教师建的内容：

1. 内置案例（created_by 为空）只有管理员能改；
2. 自建案例只有创建者本人与管理员能改；
3. 学生完全不能写。

另外锁住"保存即上架"：编辑一个曾下架的案例必须恢复可见，
否则用户会看到"保存成功但仍不可见"。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from tests.helpers import auth, login, seed_account


def scenario_body(sid: str, name: str = "李叔") -> dict:
    return {
        "id": sid,
        "name": name,
        "age": 52,
        "gender": "男",
        "archetype": "失业中年人",
        "difficulty": 3,
        "resistance": 3,
        "sensitive_tag": "无",
        "brief": "工厂倒闭后失业两年。",
        "initial_emotion": 35,
        "system_prompt": "你扮演 52 岁失业男性。",
        "voice_low": "……有啥好说的。",
        "voice_mid": "嗯，还行吧。",
        "voice_high": "你能帮我问问厂里还要人不？",
    }


async def _as(client, username: str) -> dict[str, str]:
    """用 helper 的默认口令登录（种子账号统一用 PASSWORD）。"""
    r = await login(client, username)
    return auth(r["tokens"]["access_token"])


@pytest.mark.asyncio
async def test_teacher_can_create_scenario(api):
    application, client = await api()
    await seed_account(application, username="tcr", nickname="张老师", role=Role.TEACHER)
    h = await _as(client, "tcr")

    r = await client.post("/api/v1/teacher/scenarios", headers=h, json=scenario_body("X-101"))
    assert r.status_code == 200, r.text

    rows = (await client.get("/api/v1/teacher/scenarios", headers=h)).json()["data"]["items"]
    mine = next(x for x in rows if x["id"] == "X-101")
    assert mine["custom"] is True
    assert mine["editable"] is True
    assert mine["owner_name"] == "张老师"
    assert mine["active"] is True, "新建案例应直接上架"


@pytest.mark.asyncio
async def test_student_sees_teacher_scenario(api):
    application, client = await api()
    await seed_account(application, username="tcr2", nickname="李老师", role=Role.TEACHER)
    await seed_account(application, username="stu2", nickname="学生甲", role=Role.STUDENT)
    ht = await _as(client, "tcr2")
    hs = await _as(client, "stu2")

    await client.post("/api/v1/teacher/scenarios", headers=ht, json=scenario_body("X-102"))
    items = (await client.get("/api/v1/scenarios", headers=hs)).json()["data"]["items"]
    assert any(x["id"] == "X-102" for x in items), "学生必须能看到教师新建的案例"
    row = next(x for x in items if x["id"] == "X-102")
    assert row["editable"] is False, "学生不可编辑"


@pytest.mark.asyncio
async def test_teacher_cannot_edit_builtin(api):
    application, client = await api()
    await seed_account(application, username="tcr3", nickname="王老师", role=Role.TEACHER)
    h = await _as(client, "tcr3")

    builtin = (await client.get("/api/v1/scenarios", headers=h)).json()["data"]["items"]
    target = next(x for x in builtin if not x["custom"])

    r = await client.post(
        "/api/v1/teacher/scenarios", headers=h,
        json={**scenario_body(target["id"]), "name": "篡改"},
    )
    assert r.status_code == 403, "教师不允许修改内置案例"
    d = await client.delete(f"/api/v1/teacher/scenarios/{target['id']}", headers=h)
    assert d.status_code == 403, "教师不允许下架内置案例"


@pytest.mark.asyncio
async def test_teacher_cannot_edit_others_scenario(api):
    """两位教师之间互相隔离。"""
    application, client = await api()
    await seed_account(application, username="ta1", nickname="甲老师", role=Role.TEACHER)
    await seed_account(application, username="tb1", nickname="乙老师", role=Role.TEACHER)
    ha = await _as(client, "ta1")
    hb = await _as(client, "tb1")

    await client.post("/api/v1/teacher/scenarios", headers=ha, json=scenario_body("X-103"))
    r = await client.post(
        "/api/v1/teacher/scenarios", headers=hb,
        json={**scenario_body("X-103"), "name": "乙老师改名"},
    )
    assert r.status_code == 403, "教师不能改别人建的案例"

    # 乙老师能看到但不可编辑
    rows = (await client.get("/api/v1/teacher/scenarios", headers=hb)).json()["data"]["items"]
    row = next(x for x in rows if x["id"] == "X-103")
    assert row["editable"] is False
    assert row["owner_name"] == "甲老师"


@pytest.mark.asyncio
async def test_admin_can_edit_any_scenario(api):
    application, client = await api()
    await seed_account(application, username="tcr4", nickname="赵老师", role=Role.TEACHER)
    await seed_account(application, username="adm1", nickname="管理员", role=Role.ADMIN)
    ht = await _as(client, "tcr4")
    ha = await _as(client, "adm1")

    await client.post("/api/v1/teacher/scenarios", headers=ht, json=scenario_body("X-104"))
    r = await client.post(
        "/api/v1/admin/scenarios", headers=ha,
        json={**scenario_body("X-104"), "name": "管理员改名"},
    )
    assert r.status_code == 200, "管理员应能编辑教师自建的案例"

    builtin = next(
        x for x in (await client.get("/api/v1/scenarios", headers=ha)).json()["data"]["items"]
        if not x["custom"]
    )
    r2 = await client.post(
        "/api/v1/admin/scenarios", headers=ha,
        json={**scenario_body(builtin["id"]), "name": builtin["name"]},
    )
    assert r2.status_code == 200, "管理员应能编辑内置案例"


@pytest.mark.asyncio
async def test_student_cannot_write_scenarios(api):
    application, client = await api()
    await seed_account(application, username="stu3", nickname="学生乙", role=Role.STUDENT)
    h = await _as(client, "stu3")

    r = await client.post("/api/v1/teacher/scenarios", headers=h, json=scenario_body("X-105"))
    assert r.status_code == 403
    r2 = await client.post("/api/v1/admin/scenarios", headers=h, json=scenario_body("X-106"))
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_editing_archived_scenario_restores_it(api):
    """保存即上架：编辑一个曾下架的案例要重新可见。

    不加这条会出现"保存成功但学生仍看不到"的困惑。
    """
    application, client = await api()
    await seed_account(application, username="tcr5", nickname="孙老师", role=Role.TEACHER)
    h = await _as(client, "tcr5")

    await client.post("/api/v1/teacher/scenarios", headers=h, json=scenario_body("X-107"))
    await client.delete("/api/v1/teacher/scenarios/X-107", headers=h)
    items = (await client.get("/api/v1/scenarios", headers=h)).json()["data"]["items"]
    assert not any(x["id"] == "X-107" for x in items), "下架后不应出现在列表"

    r = await client.post(
        "/api/v1/teacher/scenarios", headers=h,
        json={**scenario_body("X-107"), "name": "重新上架"},
    )
    assert r.status_code == 200
    items = (await client.get("/api/v1/scenarios", headers=h)).json()["data"]["items"]
    row = next((x for x in items if x["id"] == "X-107"), None)
    assert row is not None, "再次保存后应恢复可见"
    assert row["active"] is True
    assert row["name"] == "重新上架"

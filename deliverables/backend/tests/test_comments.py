"""教师点评测试。

除常规权限外，重点覆盖三件容易在真实项目里出错的事：
1. **写入是否真的落库**——`get_session` 只在异常时回滚，成功路径不提交，
   服务层漏写 commit 时接口会返回 200 但数据丢失；
2. **未读标记的读时更新**——学员查看后必须真的持久化，否则红点永远不消失；
3. **越权返回 403 而非 404**——记录对学生本身可见，返回 404 会误导成"记录被删"。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from tests.helpers import auth, create_session, login, seed_account, submit_turn


async def _teacher_with_learner(application, client):
    """教师 + 名下学员 + 一条已结算的训练记录。"""
    teacher = await seed_account(
        application, username="cteach", nickname="点评教师", role=Role.TEACHER
    )
    learner = await seed_account(application, username="clearn", nickname="点评学员")
    async with application.state.db.session() as session:
        target = await session.get(type(learner), learner.id)
        target.teacher_id = teacher.id
        await session.commit()

    l_headers = auth((await login(client, "clearn"))["tokens"]["access_token"])
    t_headers = auth((await login(client, "cteach"))["tokens"]["access_token"])

    created = await create_session(client, l_headers, scenario_id="W-01")
    sid = created["id"]
    await submit_turn(client, l_headers, sid, text="王阿姨您好，我是社区的小陈。")
    await client.post(f"/api/v1/sessions/{sid}/stages/1/score", headers=l_headers, json={})
    await client.post(f"/api/v1/sessions/{sid}/finish", headers=l_headers, json={})

    async with application.state.db.session() as session:
        from sqlalchemy import select

        from app.domain.models import TrainingRecord

        record = (
            await session.execute(
                select(TrainingRecord).where(TrainingRecord.owner_id == learner.id)
            )
        ).scalars().first()
    return teacher, learner, t_headers, l_headers, record, sid


@pytest.mark.asyncio
async def test_teacher_can_comment_and_it_persists(api):
    """点评必须真的落库——只 flush 不 commit 时接口仍返回 200，但数据丢失。"""
    application, client = await api()
    _, _, t_headers, l_headers, record, _ = await _teacher_with_learner(application, client)

    resp = await client.post(
        f"/api/v1/teacher/comments?record_id={record.id}",
        headers=t_headers,
        json={"content": "同感回应到位，建议下次先探索再给建议。", "level": "watch"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["level_label"] == "需关注"

    # 关键：换一个新请求重新读取，能读到才算真的落库
    again = await client.get("/api/v1/teacher/comments", headers=t_headers,
                             params={"record_id": str(record.id)})
    assert again.status_code == 200
    assert again.json()["data"]["total"] == 1, "点评未持久化（漏 commit）"


@pytest.mark.asyncio
async def test_learner_sees_own_comments_and_unread_turns_read(api):
    """学员能看自己的点评，且首次查看后未读归零并持久化。"""
    application, client = await api()
    _, learner, t_headers, l_headers, record, _ = await _teacher_with_learner(
        application, client
    )

    await client.post(
        f"/api/v1/teacher/comments?record_id={record.id}",
        headers=t_headers,
        json={"content": "这次进步明显。", "level": "good"},
    )

    first = await client.get("/api/v1/comments/mine", headers=l_headers)
    assert first.status_code == 200
    data = first.json()["data"]
    assert data["total"] == 1
    assert data["unread"] == 1, "新建点评应计为未读"

    # 第二次读取，未读应已清零
    second = await client.get("/api/v1/comments/mine", headers=l_headers)
    assert second.json()["data"]["unread"] == 0, "已读标记没有持久化"

    # 未读计数接口也应返回 0
    unread = await client.get("/api/v1/comments/unread", headers=l_headers)
    assert unread.json()["data"]["unread"] == 0


@pytest.mark.asyncio
async def test_teacher_cannot_comment_other_learners_record(api):
    """教师点评非名下学员的记录返回 403。"""
    application, client = await api()
    _, _, t_headers, _, _, _ = await _teacher_with_learner(application, client)

    outsider = await seed_account(application, username="coutsider", nickname="外来学员")
    o_headers = auth((await login(client, "coutsider"))["tokens"]["access_token"])
    created = await create_session(client, o_headers, scenario_id="W-01")
    sid = created["id"]
    await submit_turn(client, o_headers, sid, text="您好。")
    await client.post(f"/api/v1/sessions/{sid}/stages/1/score", headers=o_headers, json={})
    await client.post(f"/api/v1/sessions/{sid}/finish", headers=o_headers, json={})

    async with application.state.db.session() as session:
        from sqlalchemy import select

        from app.domain.models import TrainingRecord

        rec = (
            await session.execute(
                select(TrainingRecord).where(TrainingRecord.owner_id == outsider.id)
            )
        ).scalars().first()

    resp = await client.post(
        f"/api/v1/teacher/comments?record_id={rec.id}",
        headers=t_headers,
        json={"content": "越权", "level": "good"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_call_teacher_comment_api(api):
    """学生调教师端点评接口一律 403。"""
    application, client = await api()
    _, _, _, l_headers, record, _ = await _teacher_with_learner(application, client)

    resp = await client.post(
        f"/api/v1/teacher/comments?record_id={record.id}",
        headers=l_headers,
        json={"content": "学生越权", "level": "good"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missing_record_returns_404(api):
    application, client = await api()
    _, _, t_headers, _, _, _ = await _teacher_with_learner(application, client)

    resp = await client.post(
        "/api/v1/teacher/comments?record_id=00000000-0000-0000-0000-000000000000",
        headers=t_headers,
        json={"content": "x", "level": "good"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_content_rejected(api):
    """空内容被拒。本项目把 RequestValidationError 统一映射为 400，不是 422。"""
    application, client = await api()
    _, _, t_headers, _, record, _ = await _teacher_with_learner(application, client)

    resp = await client.post(
        f"/api/v1/teacher/comments?record_id={record.id}",
        headers=t_headers,
        json={"content": "", "level": "good"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_only_author_or_admin_can_delete(api):
    """只有作者本人或管理员能删点评。"""
    application, client = await api()
    _, _, t_headers, l_headers, record, _ = await _teacher_with_learner(
        application, client
    )

    created = await client.post(
        f"/api/v1/teacher/comments?record_id={record.id}",
        headers=t_headers,
        json={"content": "待删除", "level": "good"},
    )
    cid = created.json()["data"]["id"]

    # 学员不能删
    deny = await client.delete(f"/api/v1/teacher/comments/{cid}", headers=l_headers)
    assert deny.status_code == 403

    # 作者本人可以删
    ok = await client.delete(f"/api/v1/teacher/comments/{cid}", headers=t_headers)
    assert ok.status_code == 200

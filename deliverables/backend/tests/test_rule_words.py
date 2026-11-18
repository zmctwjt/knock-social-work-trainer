"""判定词表运行时覆盖测试。

重点验证三件事：
1. 追加的正向词条真的进入判定（不是只落库）；
2. 危机组禁止禁用（安全边界不可被接口削弱）；
3. 非危机组禁用基线词后不再命中，重新追加可恢复。
"""

from __future__ import annotations

import pytest

from app.domain import rules
from app.domain.enums import Role
from tests.helpers import auth, login, seed_account


async def _admin_token(application, client) -> str:
    await seed_account(application, username="root01", nickname="管理员", role=Role.ADMIN)
    return (await login(client, "root01"))["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_list_rule_word_groups(api):
    application, client = await api()
    token = await _admin_token(application, client)

    body = (await client.get("/api/v1/admin/rule-words", headers=auth(token))).json()
    assert body["code"] == 0
    groups = {g["group"]: g for g in body["data"]["groups"]}
    assert groups["crisis"]["baseline"] > 0
    assert groups["crisis"]["protected"] is True
    assert groups["empathy"]["protected"] is False
    # 基线为 9 张词表共 165 条（另有 6 条封闭提问后缀不可维护，见 rules.py）
    assert sum(g["baseline"] for g in body["data"]["groups"]) == 165


@pytest.mark.asyncio
async def test_added_word_takes_effect_in_matcher(api):
    """新增同感词后，含该词的输入应立即被判为共情。"""
    application, client = await api()
    token = await _admin_token(application, client)

    sentence = "我知道你心里堵得慌"
    before = rules.match_local_rules(sentence)
    assert before.intent.value != "共情" or not before.hit_words

    resp = await client.post(
        "/api/v1/admin/rule-words",
        headers=auth(token),
        json={"group": "empathy", "word": "心里堵得慌", "note": "学生口语常用"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["effective"] > 0

    after = rules.match_local_rules(sentence)
    assert "心里堵得慌" in after.hit_words, "新词应进入判定"
    assert after.intent.value == "共情"


@pytest.mark.asyncio
async def test_crisis_group_cannot_be_disabled(api):
    """危机组禁禁用：接口必须拒绝，避免误操作削弱安全边界。"""
    application, client = await api()
    token = await _admin_token(application, client)

    resp = await client.delete(
        "/api/v1/admin/rule-words/crisis/不想活", headers=auth(token)
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == 40301

    # 危机判定仍然有效
    result = rules.match_local_rules("我真的不想活了")
    assert result.intent.value == "危机"
    assert result.risk_level.value == "suicidal"


@pytest.mark.asyncio
async def test_disable_then_restore_baseline_word(api):
    """禁用基线词后不再命中；再次追加即恢复。"""
    application, client = await api()
    token = await _admin_token(application, client)

    probe = "我理解你"
    assert rules.match_local_rules(probe).hit_words, "前置条件：基线应命中"

    off = await client.delete("/api/v1/admin/rule-words/empathy/我理解", headers=auth(token))
    assert off.status_code == 200, off.text
    hits = rules.match_local_rules(probe).hit_words
    assert "我理解" not in hits, f"禁用后不应命中，实际 {hits}"

    back = await client.post(
        "/api/v1/admin/rule-words", headers=auth(token),
        json={"group": "empathy", "word": "我理解"},
    )
    assert back.status_code == 200
    hits2 = rules.match_local_rules(probe).hit_words
    assert "我理解" in hits2, f"恢复后应重新命中，实际 {hits2}"


@pytest.mark.asyncio
async def test_duplicate_word_rejected(api):
    application, client = await api()
    token = await _admin_token(application, client)

    payload = {"group": "off_topic", "word": "今天天气不错"}
    first = await client.post("/api/v1/admin/rule-words", headers=auth(token), json=payload)
    assert first.status_code == 200
    second = await client.post("/api/v1/admin/rule-words", headers=auth(token), json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_unknown_group_rejected(api):
    application, client = await api()
    token = await _admin_token(application, client)
    resp = await client.post(
        "/api/v1/admin/rule-words", headers=auth(token),
        json={"group": "not_a_group", "word": "随便"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_student_cannot_touch_rule_words(api):
    application, client = await api()
    await seed_account(application, username="stu777", nickname="学员")
    token = (await login(client, "stu777"))["tokens"]["access_token"]

    for method, path in (
        ("get", "/api/v1/admin/rule-words"),
        ("post", "/api/v1/admin/rule-words"),
    ):
        if method == "get":
            resp = await client.get(path, headers=auth(token))
        else:
            resp = await client.post(
                path, headers=auth(token), json={"group": "empathy", "word": "测试"}
            )
        assert resp.status_code == 403
        assert resp.json()["code"] == 40301

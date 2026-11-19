"""判定词表公开视图。

任务书要求学员端知识库能"查阅技巧卡、伦理守则与判定词表"。
管理端接口只返回数量与自定义条目（给维护者看），
学员要看具体词条，因此单独提供只读公开视图。这组测试锁住：
1. 不需要登录也能读（知识库对未登录开放）；
2. 九个分组齐全、每组词条非空；
3. 危机 / 无望感受两组标记为受保护（基线词不可禁用）；
4. 公开视图是只读的——不存在写接口。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_wordbook_public_without_login(api):
    _, client = await api()
    r = await client.get("/api/v1/rule-words")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] > 100, f"词条总数应上百，实际 {data['total']}"
    assert len(data["groups"]) == 9


@pytest.mark.asyncio
async def test_wordbook_groups_have_words(api):
    _, client = await api()
    groups = (await client.get("/api/v1/rule-words")).json()["data"]["groups"]
    for g in groups:
        assert g["words"], f"分组 {g['group']} 没有词条"
        assert g["count"] == len(g["words"])
        assert g["label"], f"分组 {g['group']} 缺中文标签"


@pytest.mark.asyncio
async def test_wordbook_protected_groups_marked(api):
    """危机与无望感受承载安全边界，必须明确标记为受保护。"""
    _, client = await api()
    groups = (await client.get("/api/v1/rule-words")).json()["data"]["groups"]
    by_name = {g["group"]: g for g in groups}
    assert by_name["crisis"]["protected"] is True
    assert by_name["hopelessness"]["protected"] is True
    # 普通分组不应误标
    assert by_name["empathy"]["protected"] is False


@pytest.mark.asyncio
async def test_wordbook_has_no_write_endpoint(api):
    """公开路径必须是只读的，写操作只能在 /admin 下。"""
    application, client = await api()
    paths = application.openapi()["paths"]
    public = paths["/api/v1/rule-words"]
    assert set(public.keys()) == {"get"}, f"公开词表不应有写方法：{list(public.keys())}"

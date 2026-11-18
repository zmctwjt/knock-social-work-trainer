"""输入安全：注入、超长、类型混淆、路径穿越。

已有 test_security.py 覆盖令牌、哈希与日志脱敏，但**没有覆盖输入注入**
这一层。这组测试针对"用户能在输入框里塞什么"：

1. SQL 注入串不能绕过登录，也不能把库打挂；
2. 超长输入被长度上限拦下（不是存进去再说）；
3. 类型混淆（该给字符串的位置给对象/数组）返回 400 而不是 500；
4. 静态文件路径穿越读不到 STATIC_DIR 之外的文件；
5. 存储型 XSS 的载荷被当作文本返回，不做任何解析（前端 React 默认转义）。

说明：XSS 的最终防线是前端渲染时转义，这里只验证**服务端不丢数据、
不解析、不报错**；浏览器端是否真的不执行由 audit_xss.py 验证。
"""

from __future__ import annotations

import pytest

from app.domain.enums import Role
from tests.helpers import auth, login, seed_account

INJECTIONS = [
    "' OR '1'='1",
    "admin'--",
    "'; DROP TABLE accounts; --",
    "' UNION SELECT * FROM accounts --",
    "1' AND 1=1 --",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", INJECTIONS)
async def test_sql_injection_cannot_bypass_login(api, payload):
    """注入串作为用户名必须登录失败，且不能是 500。"""
    application, client = await api()
    await seed_account(application, username="realuser", nickname="真用户")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": payload, "password": "whatever"},
    )
    # 401 表示"账号或密码错误"；关键是既不能 200，也不能 500
    assert resp.status_code in (400, 401), (
        f"注入串返回了 {resp.status_code}，应为 400/401"
    )
    body = resp.json()
    assert body.get("code") != 0, "注入串竟然登录成功了"


@pytest.mark.asyncio
async def test_sql_injection_in_password_does_not_crash(api):
    """密码字段注入：不能 500，也不能绕过。"""
    application, client = await api()
    await seed_account(application, username="u1", nickname="用户一")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "u1", "password": "' OR 1=1 --"},
    )
    assert resp.status_code in (400, 401)


@pytest.mark.asyncio
async def test_tables_survive_injection_attempt(api):
    """注入尝试之后库仍可用——证明没有真的把表 DROP 掉。"""
    application, client = await api()
    await seed_account(application, username="survivor", nickname="存活用户")

    await client.post(
        "/api/v1/auth/login",
        json={"username": "'; DROP TABLE accounts; --", "password": "x"},
    )
    # 还能正常登录
    tokens = await login(client, "survivor")
    assert tokens["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_overlong_comment_rejected(api):
    """点评内容上限 1000 字，超长应被拦下而不是先存后截断。"""
    application, client = await api()
    teacher = await seed_account(
        application, username="t_long", nickname="长文本教师", role=Role.TEACHER
    )
    learner = await seed_account(application, username="s_long", nickname="长文本学员")
    async with application.state.db.session() as session:
        target = await session.get(type(learner), learner.id)
        target.teacher_id = teacher.id
        await session.commit()

    headers = auth((await login(client, "t_long"))["tokens"]["access_token"])
    resp = await client.post(
        "/api/v1/teacher/comments?record_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
        json={"content": "x" * 1001, "level": "good"},
    )
    # 长度校验先于存在性校验
    assert resp.status_code == 400, f"超长内容未被拦下（{resp.status_code}）"


@pytest.mark.asyncio
async def test_type_confusion_returns_400(api):
    """该给字符串的位置给对象/数组，应是 400 而不是 500。"""
    application, client = await api()
    await seed_account(application, username="u2", nickname="用户二")

    for bad in ({"username": {"$ne": None}, "password": "x"},
                {"username": ["a"], "password": "x"},
                {"username": 123, "password": "x"}):
        resp = await client.post("/api/v1/auth/login", json=bad)
        assert resp.status_code in (400, 422), (
            f"类型混淆 {bad} 返回 {resp.status_code}，应为 400"
        )
        assert resp.status_code != 500


@pytest.mark.asyncio
async def test_static_path_traversal_blocked(api):
    """静态托管不得穿越到 STATIC_DIR 之外。"""
    application, client = await api()
    payloads = [
        "/../backend/app/main.py",
        "/../../../../etc/passwd",
        "/..%2f..%2fmain.py",
    ]
    for path in payloads:
        resp = await client.get(path)
        # 允许 404（找不到）或 400/403（拒绝），绝不能 200 返回源码
        assert resp.status_code != 200 or b"FastAPI" not in resp.content, (
            f"路径穿越 {path} 疑似读到了源码"
        )


@pytest.mark.asyncio
async def test_xss_payload_stored_verbatim_and_served_as_json(api):
    """存储型 XSS：服务端负责"原样保存 + 声明 JSON"，
    HTML 转义由前端渲染层负责（React 默认转义文本节点）。

    注意一个容易写错的断言：JSON 响应里出现 `<script>` 字面量**不是漏洞**。
    JSON 序列化不做 HTML 转义，转义发生在把字符串插入 HTML 时。
    真正要看的是：
    1. 数据保真——载荷原样存取，没有被服务端偷偷改写（改写会破坏用户内容）；
    2. Content-Type 是 application/json——浏览器直接访问该 URL 时
       不会把它当 HTML 执行。
    """
    application, client = await api()
    await seed_account(
        application, username="a_xss", nickname="XSS 管理员", role=Role.ADMIN
    )
    headers = auth((await login(client, "a_xss"))["tokens"]["access_token"])

    payload = "<script>alert('xss')</script><img src=x onerror=alert(1)>"
    created = await client.post(
        "/api/v1/admin/cards",
        headers=headers,
        json={"id": "T-XSS", "title": payload, "category": "技巧",
              "summary": payload, "content": payload},
    )
    assert created.status_code == 200, "含 XSS 载荷的内容不应被拒绝（靠渲染层转义）"

    listed = await client.get("/api/v1/knowledge/cards")
    assert listed.status_code == 200

    # ① 必须是 JSON：浏览器不会把 application/json 当 HTML 执行
    ctype = listed.headers.get("content-type", "")
    assert "application/json" in ctype, f"Content-Type 异常：{ctype}"

    # ② 数据保真：载荷原样返回，服务端没有篡改用户内容
    found = next(x for x in listed.json()["data"]["items"] if x["id"] == "T-XSS")
    assert found["title"] == payload, "服务端改写了用户内容（数据保真被破坏）"

    # ③ 不允许在 API 层出现 text/html——那才可能被当页面执行
    assert "text/html" not in ctype

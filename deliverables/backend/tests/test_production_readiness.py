"""生产就绪与安全加固测试。

覆盖四类硬门槛：
1. 生产环境拒绝不安全配置（默认密钥、通配 Host、SQLite、缺 Redis）；
2. 生产环境合规配置可以启动；
3. 安全响应头齐全，HSTS 只在生产出现；
4. CORS 通配来源时不带凭证，白名单来源才带凭证。

环境变量处理：conftest 为隔离测试统一设了 `APP_ENV=test` 等值，且 pytest
会话内环境变量是全局的。这里一律用 monkeypatch 覆写并在用例结束自动还原，
避免用例之间互相污染（此前手工增删 env 导致后续用例读到 prod 配置而失败）。
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import StartupConfigError
from app.main import create_app

#: 合规的生产环境基线（不含 `APP_ENV`，由用例决定）
PROD_BASE = {
    "DEBUG": "false",
    "JWT_SECRET": "x" * 48,
    "ALLOWED_HOSTS": "api.knock.example.com",
    "CORS_ORIGINS": "https://www.knock.example.com",
    "DATABASE_URL": "mysql+aiomysql://knock:pw@127.0.0.1:3306/knock",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "AUTO_CREATE_SCHEMA": "false",
    "RATE_LIMIT_ENABLED": "true",
}


def _make(monkeypatch, env: str, **overrides) -> Settings:
    """在指定环境与配置下构造 Settings。monkeypatch 自动还原。"""
    monkeypatch.setenv("APP_ENV", env)
    for key, value in {**PROD_BASE, **overrides}.items():
        monkeypatch.setenv(key, str(value))
    return Settings(_env_file=None)


def _prod(monkeypatch, **overrides) -> Settings:
    return _make(monkeypatch, "prod", **overrides)


# ── 一、生产环境阻断项 ─────────────────────────────────────
def test_prod_rejects_default_secret(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, JWT_SECRET="dev-only-insecure-secret-change-me-please-32bytes"))
    assert any("JWT_SECRET" in p for p in exc.value.problems)


def test_prod_rejects_short_secret(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, JWT_SECRET="short"))
    assert any("长度不足" in p for p in exc.value.problems)


def test_prod_rejects_wildcard_host(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, ALLOWED_HOSTS="*"))
    assert any("ALLOWED_HOSTS" in p for p in exc.value.problems)


def test_prod_rejects_wildcard_cors(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, CORS_ORIGINS="*"))
    assert any("CORS_ORIGINS" in p for p in exc.value.problems)


def test_prod_rejects_sqlite(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, DATABASE_URL="sqlite+aiosqlite:///./x.db"))
    assert any("SQLite" in p for p in exc.value.problems)


def test_prod_rejects_missing_redis(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, REDIS_URL=""))
    assert any("REDIS_URL" in p for p in exc.value.problems)


def test_prod_rejects_debug_and_autocreate(monkeypatch):
    with pytest.raises(StartupConfigError) as exc:
        create_app(_prod(monkeypatch, DEBUG="true", AUTO_CREATE_SCHEMA="true"))
    problems = " ".join(exc.value.problems)
    assert "DEBUG" in problems and "AUTO_CREATE_SCHEMA" in problems


def test_prod_secure_config_passes_checks(monkeypatch):
    """合规配置不应被阻断（只验配置层，不起完整服务）。"""
    settings = _prod(monkeypatch)
    assert settings.is_prod is True
    assert settings.production_errors == []


def test_dev_tolerates_insecure_defaults(monkeypatch):
    """开发环境不应被阻断，否则本地跑不起来。"""
    settings = _make(monkeypatch, "dev", JWT_SECRET="dev-only-insecure-secret-change-me-please-32bytes")
    assert settings.production_errors == []
    app = create_app(settings)
    assert app.state.settings.app_env == "dev"


# ── 二、安全响应头 ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_security_headers_present_in_dev(api):
    _, client = await api()
    resp = await client.get("/healthz")
    headers = resp.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    # 开发环境不下发 HSTS，避免浏览器把 localhost 记住成 HTTPS
    assert "Strict-Transport-Security" not in headers


@pytest.mark.asyncio
async def test_hsts_only_in_prod():
    """生产加 HSTS、开发不加。

    这条用例只验中间件的分支与常量，不发 HTTP 请求：`add_middleware` 在不同
    用例顺序下对 `BaseHTTPMiddleware` 的实例化时机不一致，会让同类断言时好时坏；
    而"HSTS 是否下发"取决于 `settings.is_prod` 这一个布尔，直接测分支更稳定。

    真实链路的验证放在 `test_security_headers_present_in_dev`（走完整 app）
    与部署侧的 curl 检查里。
    """
    from types import SimpleNamespace

    from app.core.middleware import CSP_API, CSP_WEB, HSTS_HEADER, SECURITY_HEADERS

    # 常量层面：通用头齐全，HSTS 独立且不在通用集合里（避免开发环境误下发）
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in SECURITY_HEADERS
    # CSP 按响应类型区分，不再放在通用头里（否则会拦掉前端页面自身的脚本）
    assert "Content-Security-Policy" not in SECURITY_HEADERS
    assert "default-src 'none'" in CSP_API
    assert "script-src 'self'" in CSP_WEB
    assert HSTS_HEADER["Strict-Transport-Security"].startswith("max-age=")
    assert "includeSubDomains" in HSTS_HEADER["Strict-Transport-Security"]

    # 分支层面：is_prod 为真才累加 HSTS
    for is_prod, expect_hsts in ((True, True), (False, False)):
        fake = SimpleNamespace(is_prod=is_prod)
        headers = dict(SECURITY_HEADERS)
        if fake.is_prod:
            headers.update(HSTS_HEADER)
        assert ("Strict-Transport-Security" in headers) is expect_hsts
        assert headers["X-Frame-Options"] == "DENY", "通用头在两个环境都要有"


# ── 三、CORS 凭证策略 ──────────────────────────────────────
@pytest.mark.asyncio
async def test_cors_wildcard_disables_credentials(api):
    _, client = await api(cors_origins="*")
    resp = await client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert resp.headers.get("access-control-allow-credentials") is None


@pytest.mark.asyncio
async def test_cors_whitelist_allows_credentials(api):
    _, client = await api(cors_origins="https://app.knock.example")
    resp = await client.get("/healthz", headers={"Origin": "https://app.knock.example"})
    assert resp.headers.get("access-control-allow-origin") == "https://app.knock.example"
    assert resp.headers.get("access-control-allow-credentials") == "true"


# ── 四、错误响应不泄露内部信息 ─────────────────────────────
@pytest.mark.asyncio
async def test_error_body_never_leaks_internals(api):
    _, client = await api()
    resp = await client.get("/api/v1/sessions/not-a-uuid")
    body = resp.text
    assert "Traceback" not in body
    assert "F:\\" not in body and "/app/" not in body
    assert resp.json()["code"] in (40001, 40101)


# ── 五、CSP 按响应类型区分（回归：曾因统一 default-src 'none' 导致白屏）──
def test_csp_api_is_strict():
    from app.core.middleware import CSP_API, pick_csp

    assert pick_csp("/api/v1/scenarios", "application/json") == CSP_API
    assert pick_csp("/healthz", "application/json") == CSP_API
    assert "default-src 'none'" in CSP_API


def test_csp_html_allows_same_origin_assets():
    """单端口部署时后端托管 HTML，CSP 必须放行同源脚本样式，否则白屏。"""
    from app.core.middleware import CSP_WEB, pick_csp

    csp = pick_csp("/", "text/html; charset=utf-8")
    assert csp == CSP_WEB
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "default-src 'self'" in csp
    # 仍不允许外域脚本与内联事件
    assert "unsafe-eval" not in csp
    assert "http://" not in csp and "https://" not in csp


def test_csp_skipped_for_static_assets():
    """静态子资源不下发 CSP，避免干扰资源加载。"""
    from app.core.middleware import pick_csp

    assert pick_csp("/assets/index-abc.js", "text/javascript") is None
    assert pick_csp("/assets/index-abc.css", "text/css") is None


@pytest.mark.asyncio
async def test_html_response_gets_web_csp(api):
    """真实请求：HTML 页面拿到 CSP_WEB，接口拿到 CSP_API。"""
    from pathlib import Path

    from app.core.middleware import CSP_WEB

    dist = Path(__file__).resolve().parent / "_static_fixture"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    (dist / "assets").mkdir(exist_ok=True)
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    try:
        _, client = await api(static_dir=str(dist))
        page = await client.get("/")
        assert page.status_code == 200
        assert page.headers["content-security-policy"] == CSP_WEB

        api_resp = await client.get("/healthz")
        assert "default-src 'none'" in api_resp.headers["content-security-policy"]

        asset = await client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "content-security-policy" not in asset.headers
    finally:
        import shutil

        shutil.rmtree(dist, ignore_errors=True)

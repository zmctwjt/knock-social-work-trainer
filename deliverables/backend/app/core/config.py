"""集中配置。

所有配置项均从环境变量读取（pydantic-settings，大小写不敏感），键名与
`env.example`、`docker-compose.yml`、附录 B 严格一致。密钥类配置一律
没有有效默认值时必须"优雅降级"而不是启动崩溃：AI 密钥缺失 → 规则模式，
JWT 密钥使用开发默认值并在生产环境告警。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["dev", "test", "prod"]


class Settings(BaseSettings):
    """应用配置（扁平命名，等价于环境变量大写形式）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── 应用 ─────────────────────────────────────────────
    app_env: AppEnv = "dev"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    port: int = 8000
    workers: int = 4
    log_level: str = "INFO"
    log_json: bool = True
    body_limit_bytes: int = 512 * 1024
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8787,http://127.0.0.1:8787"
    )
    allowed_hosts: str = "*"
    auto_create_schema: bool = False
    seed_scenarios_on_startup: bool = True
    # 留空表示不托管前端；指向已构建的静态目录即可由后端同源托管（单端口演示）
    static_dir: str = ""

    # ── 数据库 ───────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./knock_dev.db"
    database_read_url: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ── Redis（留空自动退回进程内实现）────────────────────
    redis_url: str = ""

    # ── AI 网关（与旧 Node 版 GLM_* 同名同义）────────────
    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    glm_model: str = "glm-4.7-flash"
    glm_fallback_models: str = "glm-4.5-flash,glm-4-flash"
    glm_timeout_ms: int = 45_000
    glm_daily_cap: int = 800
    glm_rpm_per_ip: int = 20
    glm_concurrency: int = 2
    glm_cache_ttl_sec: int = 600
    glm_cache_max: int = 300
    glm_breaker_failure_threshold: float = 0.5
    glm_breaker_min_samples: int = 10
    glm_breaker_open_sec: int = 30
    glm_max_retries: int = 1

    # ── 认证 ─────────────────────────────────────────────
    jwt_secret: str = "dev-only-insecure-secret-change-me-please-32bytes"  # noqa: S105 —— 与 security.DEFAULT_JWT_SECRET 一致，生产启动时被拒
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 7
    jwt_guest_ttl_hours: int = 24

    # ── 口令哈希（Argon2id）──────────────────────────────
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65_536
    argon2_parallelism: int = 4

    # ── 可观测 ───────────────────────────────────────────
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "knock-backend"
    sentry_dsn: str = ""

    # ── 限流 ─────────────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_window_sec: int = 60

    # ── 派生属性 ─────────────────────────────────────────
    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def production_errors(self) -> list[str]:
        """生产环境的启动阻断项。返回非空时 `create_app` 拒绝启动。

        这些检查对应等保与上线检查单的硬门槛：默认密钥、调试开关、通配 Host
        在开发期方便，但只要漏到生产就是可直接利用的漏洞，因此不做降级处理。
        一是默认 JWT 密钥（可伪造任意身份）、二是 DEBUG（堆栈泄露）、
        三是 ALLOWED_HOSTS 通配（Host 头攻击）、四是 CORS 通配（任意站点可带凭证调用）。
        """
        from app.core.security import DEFAULT_JWT_SECRET

        if not self.is_prod:
            return []
        errors: list[str] = []
        if self.jwt_secret == DEFAULT_JWT_SECRET:
            errors.append("JWT_SECRET 仍为默认值，任何人都能伪造令牌")
        if len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET 长度不足 32 字符")
        if self.debug:
            errors.append("DEBUG 必须为 false")
        if "*" in self.allowed_host_list:
            errors.append("ALLOWED_HOSTS 不能为 *，需填真实域名")
        if "*" in self.cors_origin_list:
            errors.append("CORS_ORIGINS 不能为 *，需填前端域名白名单")
        if self.auto_create_schema:
            errors.append("AUTO_CREATE_SCHEMA 必须为 false，生产用 alembic upgrade")
        if self.database_url.startswith("sqlite"):
            errors.append("生产必须使用 MySQL/PostgreSQL，不能用 SQLite")
        if not self.rate_limit_enabled:
            errors.append("RATE_LIMIT_ENABLED 必须为 true")
        if not self.redis_url:
            errors.append("生产必须配置 REDIS_URL，否则多副本下限流与配额不共享")
        return errors

    @property
    def fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.glm_fallback_models.split(",") if m.strip()]

    @property
    def model_chain(self) -> list[str]:
        chain = [self.glm_model, *self.fallback_model_list]
        # 去重但保持顺序：配置写重复时不应重复调用同一模型
        seen: set[str] = set()
        return [m for m in chain if m and not (m in seen or seen.add(m))]

    @property
    def ai_configured(self) -> bool:
        return bool(self.glm_api_key.strip())

    @property
    def database_is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def database_is_mysql(self) -> bool:
        return self.database_url.startswith("mysql")

    @property
    def db_dialect(self) -> str:
        """当前数据库方言名，供日志、健康检查与就绪探针使用。"""
        if self.database_is_sqlite:
            return "sqlite"
        if self.database_is_mysql:
            return "mysql"
        return "postgresql"

    @property
    def access_ttl_seconds(self) -> int:
        return self.jwt_access_ttl_min * 60

    @property
    def refresh_ttl_seconds(self) -> int:
        return self.jwt_refresh_ttl_days * 86_400

    @property
    def guest_ttl_seconds(self) -> int:
        return self.jwt_guest_ttl_hours * 3_600

    def safe_summary(self) -> dict[str, object]:
        """供 /healthz、日志与排障使用，绝不包含密钥明文。"""
        return {
            "app_env": self.app_env,
            "api_v1_prefix": self.api_v1_prefix,
            "ai": {
                "configured": self.ai_configured,
                "model": self.glm_model,
                "fallback": self.fallback_model_list,
                "thinking": "disabled",
                "timeout_ms": self.glm_timeout_ms,
                "daily_cap": self.glm_daily_cap,
                "rpm_per_ip": self.glm_rpm_per_ip,
                "concurrency": self.glm_concurrency,
            },
            "jwt": {
                "algorithm": self.jwt_algorithm,
                "access_ttl_min": self.jwt_access_ttl_min,
                "refresh_ttl_days": self.jwt_refresh_ttl_days,
                "guest_ttl_hours": self.jwt_guest_ttl_hours,
            },
            "database": self.db_dialect,
            "redis": bool(self.redis_url),
            "otel_enabled": self.otel_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程级单例；测试通过 create_app(settings=...) 注入独立实例。"""
    return Settings()

"""安全原语与可观测性原语：口令哈希、令牌、脱敏、缓存键。"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import redact, redact_text
from app.core.security import (
    decode_token,
    encode_token,
    hash_account_id,
    hash_password,
    verify_password,
)
from app.domain.enums import Role, TokenType
from app.infra.cache import build_cache_key


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, jwt_secret="unit-test-secret-0123456789abcdef")


def test_password_hash_is_argon2id_and_verifiable(settings):
    digest = hash_password("Passw0rd!2026", settings)
    assert digest.startswith("$argon2id$")
    assert verify_password("Passw0rd!2026", digest) is True
    assert verify_password("wrong-password", digest) is False


def test_token_roundtrip(settings):
    token, jti, expires_at = encode_token(
        account_id="0b0e6a6e-1111-4222-8333-444455556666",
        role=Role.TEACHER,
        token_type=TokenType.ACCESS,
        ttl_seconds=60,
        settings=settings,
        is_guest=False,
    )
    payload = decode_token(token, expected_type=TokenType.ACCESS, settings=settings)
    assert payload["sub"] == "0b0e6a6e-1111-4222-8333-444455556666"
    assert payload["role"] == "teacher"
    assert payload["typ"] == "access"
    assert payload["jti"] == jti
    assert expires_at


def test_wrong_token_type_is_rejected(settings):
    token, _jti, _exp = encode_token(
        account_id="0b0e6a6e-1111-4222-8333-444455556666",
        role=Role.STUDENT,
        token_type=TokenType.REFRESH,
        ttl_seconds=60,
        settings=settings,
        is_guest=False,
    )
    with pytest.raises(AppError) as exc:
        decode_token(token, expected_type=TokenType.ACCESS, settings=settings)
    assert exc.value.code.value == 40101


def test_garbage_token_is_rejected(settings):
    with pytest.raises(AppError):
        decode_token("not-a-jwt", expected_type=TokenType.ACCESS, settings=settings)


def test_account_hash_is_stable_and_not_reversible():
    account_id = "0b0e6a6e-1111-4222-8333-444455556666"
    first = hash_account_id(account_id)
    assert first == hash_account_id(account_id)
    assert account_id not in first
    assert len(first) >= 8


def test_redaction_masks_phone_email_and_bearer():
    text = "电话 13812345678，邮箱 zhang@example.com，头 Bearer abc.def.ghi"
    masked = redact_text(text)
    assert "13812345678" not in masked
    assert "zhang@example.com" not in masked
    assert "abc.def.ghi" not in masked


def test_redact_keeps_safe_keys_and_masks_pii():
    event = {
        "event": "request",
        "phone": "13812345678",
        "email": "zhang@example.com",
        "path": "/api/v1/sessions",
    }
    cleaned = redact(event)
    assert cleaned["event"] == "request"
    assert cleaned["path"] == "/api/v1/sessions"
    assert cleaned["phone"] != "13812345678"
    assert cleaned["email"] != "zhang@example.com"


def test_cache_key_includes_prompt_version_model_and_input():
    payload = {"system": "s", "user": "u"}
    first = build_cache_key("intent", "2026.11.1", "glm-4.7-flash", payload)
    assert build_cache_key("intent", "2026.11.1", "glm-4.7-flash", payload) == first
    # 提示词版本、模型、输入任一变化都必须换键，否则会读到旧口径的缓存
    assert build_cache_key("intent", "2026.11.2", "glm-4.7-flash", payload) != first
    assert build_cache_key("intent", "2026.11.1", "glm-4.5-flash", payload) != first
    assert build_cache_key("intent", "2026.11.1", "glm-4.7-flash", {"user": "u2"}) != first

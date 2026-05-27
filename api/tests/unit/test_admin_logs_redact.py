"""Story 10.4 AC-4 — `_redact_diff` 마스킹 유닛 테스트 (8 케이스).

화이트리스트 키(`password_hash`, `billing_key_encrypted` 등 15종)는 재귀적으로
`"***REDACTED***"` 로 치환되고, 그 외 키는 평문을 유지한다.
"""

from __future__ import annotations

from api.src.services.admin_logs_service import (
    _REDACT_KEYS,
    _REDACT_VALUE,
    _redact_diff,
)


def test_top_level_password_hash_is_redacted() -> None:
    """case 1: top-level 민감 키."""
    result = _redact_diff({"password_hash": "argon2$..."})
    assert result == {"password_hash": _REDACT_VALUE}


def test_nested_password_hash_in_before_after() -> None:
    """case 2: before/after 같은 일반 wrapper 안 민감 키도 잡힘."""
    diff = {
        "before": {"password_hash": "old$", "email": "u@d.com"},
        "after": {"password_hash": "new$", "email": "u@d.com"},
    }
    result = _redact_diff(diff)
    assert result["before"]["password_hash"] == _REDACT_VALUE
    assert result["before"]["email"] == "u@d.com"
    assert result["after"]["password_hash"] == _REDACT_VALUE
    assert result["after"]["email"] == "u@d.com"


def test_billing_key_variants_redacted() -> None:
    """case 3: billing_key / billing_key_encrypted / pg_secret_key 등 결제 키 변형."""
    diff = {
        "billing_key": "bk_xxx",
        "billing_key_encrypted": "enc_xxx",
        "pg_secret_key": "sk_xxx",
        "card_number": "4111-...",
        "payment_secret": "secret",
    }
    result = _redact_diff(diff)
    assert all(v == _REDACT_VALUE for v in result.values())


def test_list_of_dicts_each_masked() -> None:
    """case 4: list 안의 dict 도 각각 마스킹."""
    diff = [
        {"billing_key": "x", "note": "ok"},
        {"password_hash": "y", "label": "abc"},
    ]
    result = _redact_diff(diff)
    assert result[0]["billing_key"] == _REDACT_VALUE
    assert result[0]["note"] == "ok"
    assert result[1]["password_hash"] == _REDACT_VALUE
    assert result[1]["label"] == "abc"


def test_normal_keys_preserved() -> None:
    """case 5: 평문 키 — admin_grade / email 등 정상 노출."""
    diff = {
        "admin_grade": "sub_operator",
        "email": "x@d.com",
        "blocked_until": "2026-05-27T00:00:00+00:00",
    }
    result = _redact_diff(diff)
    assert result == diff


def test_none_and_empty_dict() -> None:
    """case 6: None / 빈 dict / 빈 list."""
    assert _redact_diff(None) is None
    assert _redact_diff({}) == {}
    assert _redact_diff([]) == []


def test_deep_nesting_three_levels() -> None:
    """case 7: a.b.c.password_hash 까지 깊은 중첩."""
    diff = {"a": {"b": {"c": {"password_hash": "deep"}}}}
    result = _redact_diff(diff)
    assert result["a"]["b"]["c"]["password_hash"] == _REDACT_VALUE


def test_value_dict_under_sensitive_key_replaced_wholesale() -> None:
    """case 8: 값이 dict/list 라도 민감 키면 통째로 마스킹(재귀 안 들어감)."""
    diff = {"password_hash": {"nested": "secret"}}
    result = _redact_diff(diff)
    # 단순 마스킹 — 값 자체를 REDACTED 문자열로
    assert result["password_hash"] == _REDACT_VALUE


def test_all_redact_keys_in_constant_set() -> None:
    """case 9 (bonus): SSOT 일관성 — 화이트리스트가 명시 15종 포함."""
    expected = {
        "password_hash",
        "password_hash_old",
        "billing_key_encrypted",
        "billing_key",
        "payment_secret",
        "card_number",
        "pg_secret_key",
        "kakao_access_token",
        "kakao_refresh_token",
        "naver_access_token",
        "naver_refresh_token",
        "google_access_token",
        "google_refresh_token",
        "sms_token",
        "session_token",
    }
    assert expected <= _REDACT_KEYS

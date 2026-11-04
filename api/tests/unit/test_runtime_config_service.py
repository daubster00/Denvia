"""runtime_config_service 유닛 테스트 — get_night_block_settings (Story 4.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api.src.services.runtime_config_service import (
    NightBlockSettings,
    get_night_block_settings,
)


def _make_redis(enabled_raw: str | None, active_raw: str | None) -> AsyncMock:
    """Redis mock — get() 호출 시 enabled_raw, active_raw 순서로 반환."""
    redis = AsyncMock()
    redis.get.side_effect = [enabled_raw, active_raw]
    return redis


class TestGetNightBlockSettings:
    @pytest.mark.asyncio
    async def test_toggle_on_active_true_returns_enabled_active(self):
        """토글 ON + active=true → NightBlockSettings(enabled=True, active=True)."""
        redis = _make_redis("true", "true")
        result = await get_night_block_settings(redis)
        assert result == NightBlockSettings(enabled=True, active=True)

    @pytest.mark.asyncio
    async def test_toggle_off_returns_disabled(self):
        """토글 OFF → NightBlockSettings(enabled=False, active=...)."""
        redis = _make_redis("false", "true")
        result = await get_night_block_settings(redis)
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_active_key_null_returns_active_none(self):
        """active 키 NULL → NightBlockSettings(enabled=True, active=None) — 호출자 시각 폴백."""
        redis = _make_redis("true", None)
        result = await get_night_block_settings(redis)
        assert result == NightBlockSettings(enabled=True, active=None)

    @pytest.mark.asyncio
    async def test_redis_exception_returns_fail_closed(self):
        """Redis 호출 예외 → fail-closed NightBlockSettings(enabled=True, active=None)."""
        redis = AsyncMock()
        redis.get.side_effect = Exception("redis 연결 실패")
        result = await get_night_block_settings(redis)
        assert result == NightBlockSettings(enabled=True, active=None)

    @pytest.mark.asyncio
    async def test_active_raw_value_variations(self):
        """active 다양한 truthy 값("1", "True", "on", "yes") → active=True."""
        for truthy in ("1", "True", "on", "yes"):
            redis = _make_redis("true", truthy)
            result = await get_night_block_settings(redis)
            assert result.active is True, f"'{truthy}'는 True로 해석되어야 함"

    @pytest.mark.asyncio
    async def test_active_raw_falsy_values(self):
        """active falsy 값("0", "false", "off") → active=False."""
        for falsy in ("0", "false", "off"):
            redis = _make_redis("true", falsy)
            result = await get_night_block_settings(redis)
            assert result.active is False, f"'{falsy}'는 False로 해석되어야 함"


# ──────────────────────────────────────────────────────────────────────────────
# 질문 안내 팝업 — 설정 의도 vs 실제 노출 (2026-11-03 검수 P1-8)
#
# 빈 문구 + 노출 ON 을 저장하면, 예전에는 저장 응답은 ON 인데 재조회는 OFF 로 내려와
# 관리자가 "저장이 안 됐다" 고 읽었다. 둘을 분리해 둘 다 정확하게 만든다.
# ──────────────────────────────────────────────────────────────────────────────

import pytest as _pytest  # noqa: E402

from api.src.services.runtime_config_service import (  # noqa: E402
    DEFAULT_QA_NOTICE_ENABLED,
    DEFAULT_QA_NOTICE_TEXT,
    QaNoticeConfig,
    get_qa_notice_config,
)


def _notice(enabled: bool, text: str) -> QaNoticeConfig:
    return QaNoticeConfig(
        enabled=enabled,
        text=text,
        font_size=16,
        color="#111111",
        font_weight=500,
        width=420,
    )


def test_notice_defaults_are_deleted_text_and_hidden() -> None:
    """#149 결정 ② — 문구 삭제가 기본 상태다."""
    assert DEFAULT_QA_NOTICE_TEXT == ""
    assert DEFAULT_QA_NOTICE_ENABLED is False


def test_notice_visible_requires_both_intent_and_text() -> None:
    assert _notice(True, "안내 문구").visible is True
    assert _notice(True, "").visible is False      # 빈 팝업은 띄우지 않는다
    assert _notice(True, "   ").visible is False
    assert _notice(False, "안내 문구").visible is False


class _FakeRedis:
    def __init__(self, values: dict):
        self.values = values

    async def get(self, key):
        return self.values.get(key)


@_pytest.mark.asyncio
async def test_stored_intent_survives_round_trip_even_with_empty_text() -> None:
    """저장한 노출 의도(ON)는 재조회에서도 ON 으로 보인다 — 저장 응답과 불일치 금지."""
    cfg = await get_qa_notice_config(
        _FakeRedis(
            {
                "runtime:qa_notice_enabled": "true",
                "runtime:qa_notice_text": "",
            }
        )
    )
    assert cfg.enabled is True    # 관리자가 설정한 값 그대로
    assert cfg.visible is False   # 사용자에게는 뜨지 않는다


@_pytest.mark.asyncio
async def test_missing_keys_fall_back_to_deleted_notice() -> None:
    cfg = await get_qa_notice_config(_FakeRedis({}))
    assert cfg.text == ""
    assert cfg.enabled is False
    assert cfg.visible is False

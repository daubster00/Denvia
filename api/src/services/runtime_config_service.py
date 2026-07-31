"""서비스 전체 런타임 설정 서비스 — Redis DB 3 게이트웨이.

QA flow는 ``api.src.services.qa_service`` 의 ``_resolve_*`` helper로 동일 키들을
이미 읽고 있다. 본 모듈은 컨텐츠 관리 페이지 어드민 편집 경로 전용.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from fastapi import Request
from redis.asyncio import Redis as AsyncRedis

from api.src.schemas.admin.runtime_config import (
    AnomalyThresholdsConfigResponse,
    AnomalyThresholdsConfigUpdateRequest,
    AnomalyThresholdsItem,
    AnomalyThrottleConfigResponse,
    AnomalyThrottleConfigUpdateRequest,
    LoginBruteThresholdConfigResponse,
    LoginBruteThresholdConfigUpdateRequest,
    RuntimeConfigResponse,
    RuntimeConfigUpdateRequest,
)


# 4 키 — seed_runtime_config.py 와 동일한 namespace.
KEY_SHOW_SUBSCRIBE = "runtime:show_subscribe_button"
KEY_FREE_DAILY_QUOTA = "runtime:free_daily_quota"
KEY_FREE_DELAY_ENABLED = "runtime:free_delay_enabled"
KEY_FREE_DELAY = "runtime:free_delay"
KEY_FREE_DELAY_NOTICE_TEXT = "runtime:free_delay_notice_text"
# Pro 월 질문 한도 — KST 월초 기준 리셋. qa_service 의 monthly INCR 카운터와 한 쌍.
KEY_PRO_MONTHLY_QUOTA = "runtime:pro_monthly_quota"
# #130 ① — 질문 전송 시 화면 중앙 안내 팝업. 관리자가 문구/스타일/가로폭을 편집한다.
# "오늘 하루 보지 않기"(localStorage) 는 프론트가 KST 자정 기준으로 처리하므로 서버 무관.
KEY_QA_NOTICE_ENABLED = "runtime:qa_notice_enabled"
KEY_QA_NOTICE_TEXT = "runtime:qa_notice_text"
KEY_QA_NOTICE_FONT_SIZE = "runtime:qa_notice_font_size"
KEY_QA_NOTICE_COLOR = "runtime:qa_notice_color"
KEY_QA_NOTICE_FONT_WEIGHT = "runtime:qa_notice_font_weight"
KEY_QA_NOTICE_WIDTH = "runtime:qa_notice_width"
# Story 7.1 — 쪽지함 미리보기 동시 노출 최대 개수 (관리자 CS 페이지에서 편집).
KEY_INBOX_PREVIEW_MAX_COUNT = "runtime:inbox_preview_max_count"
# 관리자 설정 — RAG 본 체인에서 사용할 채팅 모델 (기본 o4-mini, 화이트리스트 강제).
KEY_CHAT_MODEL = "runtime:chat_model"

# QA flow 기본값과 일치 (qa_service.DEFAULT_FREE_DAILY_QUOTA / DEFAULT_FREE_DELAY_SECONDS).
DEFAULT_SHOW_SUBSCRIBE = True
DEFAULT_FREE_DAILY_QUOTA = 10
DEFAULT_FREE_DELAY_ENABLED = True
DEFAULT_FREE_DELAY_SECONDS = 1
DEFAULT_FREE_DELAY_NOTICE_TEXT = "현재는 무료버전으로 답변 출력은 약 40초가량 소요됩니다."
FREE_DELAY_NOTICE_TEXT_MAX_LEN = 200
# Pro 월 한도 기본값 — Pro 구독 상품 기획상의 월 질문 횟수.
DEFAULT_PRO_MONTHLY_QUOTA = 500
DEFAULT_INBOX_PREVIEW_MAX_COUNT = 1
INBOX_PREVIEW_MAX_COUNT_MIN = 1
INBOX_PREVIEW_MAX_COUNT_MAX = 5

# #130 ① — QA 안내 팝업 기본값 + 검증 범위.
DEFAULT_QA_NOTICE_ENABLED = True
DEFAULT_QA_NOTICE_TEXT = (
    "현재 질문하신 내용에 대한 정보만 제공하며 이전에 질문하신 내용을 참고하여 "
    "정보를 제공하지 않습니다. Denvia는 매 질문을 항상 새로운 독립질문으로 처리합니다."
)
QA_NOTICE_TEXT_MAX_LEN = 500
DEFAULT_QA_NOTICE_FONT_SIZE = 16
QA_NOTICE_FONT_SIZE_MIN = 10
QA_NOTICE_FONT_SIZE_MAX = 40
DEFAULT_QA_NOTICE_COLOR = "#111111"
DEFAULT_QA_NOTICE_FONT_WEIGHT = 500
QA_NOTICE_FONT_WEIGHT_MIN = 100
QA_NOTICE_FONT_WEIGHT_MAX = 900
DEFAULT_QA_NOTICE_WIDTH = 420
QA_NOTICE_WIDTH_MIN = 280
QA_NOTICE_WIDTH_MAX = 720

# hex 색상 검증용 정규식 (#rgb / #rrggbb 허용). 위반 시 기본값으로 폴백.
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _normalize_qa_notice_text(raw: str | bytes | None) -> str:
    """QA 안내 팝업 문구 정규화 — 미설정/공백만이면 기본값, 길이 상한 강제."""
    if raw is None:
        return DEFAULT_QA_NOTICE_TEXT
    value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    stripped = value.strip()
    if not stripped:
        return DEFAULT_QA_NOTICE_TEXT
    return stripped[:QA_NOTICE_TEXT_MAX_LEN]


def _normalize_qa_notice_color(raw: str | bytes | None) -> str:
    """hex 색상 정규화 — 형식 위반 시 기본값."""
    if raw is None:
        return DEFAULT_QA_NOTICE_COLOR
    value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    stripped = value.strip()
    if not _HEX_COLOR_RE.match(stripped):
        return DEFAULT_QA_NOTICE_COLOR
    return stripped


def _clamp(raw: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, raw))

# ADR-0002 §결정 2: RAG 인수자 튜닝값 o4-mini 가 기본값. 관리자가 명시적으로 바꿀 때만 override.
DEFAULT_CHAT_MODEL = "o4-mini"
# 허용 모델 화이트리스트 — 알 수 없는 값이 들어오면 reject(400). 응답 속도/품질/비용 특성은 admin UI에서 안내.
ALLOWED_CHAT_MODELS: tuple[str, ...] = (
    "o4-mini",       # 추론 모델, 첫 토큰까지 지연 큼(스트리밍 효과 미미)
    "gpt-4o-mini",   # 가장 빠른 첫 토큰, 가장 저렴, 일반 대화 우수
    "gpt-4o",        # 빠르고 똑똑, 가격 중상
    "gpt-4-turbo",   # 매우 똑똑, 첫 토큰 약간 느림
    # GPT-5.6 계열(2026-07 출시) — 3종 모두 추론형. 로컬 실측(프로덕션 프롬프트+인덱스)에서
    # 지시 준수는 o4-mini 와 동률(만점), 속도·비용은 luna 가 o4-mini 대비 ~2배 빠르고 ~34% 저렴.
    "gpt-5.6-luna",  # 5.6 중 가장 빠르고 저렴 — 현재 모델 대체 1순위
    "gpt-5.6-terra", # 5.6 균형형 — 품질 상위, 비용 o4-mini 대비 ~1.4배
    "gpt-5.6-sol",   # 5.6 최상위(프런티어) — 최고 품질, 비용 o4-mini 대비 ~3배
)


@dataclass(frozen=True)
class QaNoticeConfig:
    """#130 ① — QA 안내 팝업 설정 묶음 (관리자 편집 + /me/quota 전달)."""

    enabled: bool
    text: str
    font_size: int      # px
    color: str          # hex (#rgb | #rrggbb)
    font_weight: int    # 100~900
    width: int          # px


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).lower() not in ("0", "false", "off", "no")


def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _normalize_notice_text(raw: str | bytes | None) -> str:
    """안내문구 정규화 — Redis 미설정/공백만이면 기본값. 길이 상한 강제."""
    if raw is None:
        return DEFAULT_FREE_DELAY_NOTICE_TEXT
    value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    stripped = value.strip()
    if not stripped:
        return DEFAULT_FREE_DELAY_NOTICE_TEXT
    return stripped[:FREE_DELAY_NOTICE_TEXT_MAX_LEN]


async def get_free_delay_notice_text(redis_runtime: AsyncRedis) -> str:
    """무료 지연 안내문구 단일 조회 — /me/quota 응답용."""
    raw = await redis_runtime.get(KEY_FREE_DELAY_NOTICE_TEXT)
    return _normalize_notice_text(raw)


async def get_pro_monthly_quota(redis_runtime: AsyncRedis) -> int:
    """Pro 월 질문 한도 조회 — 미설정/손상값 시 기본값."""
    raw = await redis_runtime.get(KEY_PRO_MONTHLY_QUOTA)
    return _to_int(raw, DEFAULT_PRO_MONTHLY_QUOTA)


async def get_qa_notice_config(redis_runtime: AsyncRedis) -> "QaNoticeConfig":
    """QA 안내 팝업 설정 조회 — /me/quota 응답 및 관리자 GET 공용.

    fail-safe: Redis 미설정/손상값이면 각 필드 기본값으로 폴백한다.
    """
    enabled_raw = await redis_runtime.get(KEY_QA_NOTICE_ENABLED)
    text_raw = await redis_runtime.get(KEY_QA_NOTICE_TEXT)
    font_size_raw = await redis_runtime.get(KEY_QA_NOTICE_FONT_SIZE)
    color_raw = await redis_runtime.get(KEY_QA_NOTICE_COLOR)
    font_weight_raw = await redis_runtime.get(KEY_QA_NOTICE_FONT_WEIGHT)
    width_raw = await redis_runtime.get(KEY_QA_NOTICE_WIDTH)

    return QaNoticeConfig(
        enabled=_to_bool(enabled_raw, DEFAULT_QA_NOTICE_ENABLED),
        text=_normalize_qa_notice_text(text_raw),
        font_size=_clamp(
            _to_int(font_size_raw, DEFAULT_QA_NOTICE_FONT_SIZE),
            QA_NOTICE_FONT_SIZE_MIN,
            QA_NOTICE_FONT_SIZE_MAX,
        ),
        color=_normalize_qa_notice_color(color_raw),
        font_weight=_clamp(
            _to_int(font_weight_raw, DEFAULT_QA_NOTICE_FONT_WEIGHT),
            QA_NOTICE_FONT_WEIGHT_MIN,
            QA_NOTICE_FONT_WEIGHT_MAX,
        ),
        width=_clamp(
            _to_int(width_raw, DEFAULT_QA_NOTICE_WIDTH),
            QA_NOTICE_WIDTH_MIN,
            QA_NOTICE_WIDTH_MAX,
        ),
    )


async def get_runtime_config(redis_runtime: AsyncRedis) -> RuntimeConfigResponse:
    show_raw = await redis_runtime.get(KEY_SHOW_SUBSCRIBE)
    quota_raw = await redis_runtime.get(KEY_FREE_DAILY_QUOTA)
    delay_enabled_raw = await redis_runtime.get(KEY_FREE_DELAY_ENABLED)
    delay_raw = await redis_runtime.get(KEY_FREE_DELAY)
    notice_raw = await redis_runtime.get(KEY_FREE_DELAY_NOTICE_TEXT)
    pro_monthly_raw = await redis_runtime.get(KEY_PRO_MONTHLY_QUOTA)
    qa_notice = await get_qa_notice_config(redis_runtime)

    return RuntimeConfigResponse(
        show_subscribe_button=_to_bool(show_raw, DEFAULT_SHOW_SUBSCRIBE),
        free_daily_quota=_to_int(quota_raw, DEFAULT_FREE_DAILY_QUOTA),
        free_delay_enabled=_to_bool(delay_enabled_raw, DEFAULT_FREE_DELAY_ENABLED),
        free_delay_seconds=_to_int(delay_raw, DEFAULT_FREE_DELAY_SECONDS),
        free_delay_notice_text=_normalize_notice_text(notice_raw),
        pro_monthly_quota=_to_int(pro_monthly_raw, DEFAULT_PRO_MONTHLY_QUOTA),
        qa_notice_enabled=qa_notice.enabled,
        qa_notice_text=qa_notice.text,
        qa_notice_font_size=qa_notice.font_size,
        qa_notice_color=qa_notice.color,
        qa_notice_font_weight=qa_notice.font_weight,
        qa_notice_width=qa_notice.width,
    )


async def update_runtime_config(
    request: Request,
    body: RuntimeConfigUpdateRequest,
    redis_runtime: AsyncRedis,
) -> RuntimeConfigResponse:
    before = await get_runtime_config(redis_runtime)

    await redis_runtime.set(KEY_SHOW_SUBSCRIBE, "true" if body.show_subscribe_button else "false")
    await redis_runtime.set(KEY_FREE_DAILY_QUOTA, str(body.free_daily_quota))
    await redis_runtime.set(KEY_FREE_DELAY_ENABLED, "true" if body.free_delay_enabled else "false")
    await redis_runtime.set(KEY_FREE_DELAY, str(body.free_delay_seconds))
    notice_normalized = _normalize_notice_text(body.free_delay_notice_text)
    await redis_runtime.set(KEY_FREE_DELAY_NOTICE_TEXT, notice_normalized)
    await redis_runtime.set(KEY_PRO_MONTHLY_QUOTA, str(body.pro_monthly_quota))

    # #130 ① — QA 안내 팝업 6종 저장. 문구/색상은 정규화, 숫자는 clamp 후 SET.
    qa_notice_text = _normalize_qa_notice_text(body.qa_notice_text)
    qa_notice_color = _normalize_qa_notice_color(body.qa_notice_color)
    qa_notice_font_size = _clamp(
        body.qa_notice_font_size, QA_NOTICE_FONT_SIZE_MIN, QA_NOTICE_FONT_SIZE_MAX
    )
    qa_notice_font_weight = _clamp(
        body.qa_notice_font_weight, QA_NOTICE_FONT_WEIGHT_MIN, QA_NOTICE_FONT_WEIGHT_MAX
    )
    qa_notice_width = _clamp(
        body.qa_notice_width, QA_NOTICE_WIDTH_MIN, QA_NOTICE_WIDTH_MAX
    )
    await redis_runtime.set(
        KEY_QA_NOTICE_ENABLED, "true" if body.qa_notice_enabled else "false"
    )
    await redis_runtime.set(KEY_QA_NOTICE_TEXT, qa_notice_text)
    await redis_runtime.set(KEY_QA_NOTICE_FONT_SIZE, str(qa_notice_font_size))
    await redis_runtime.set(KEY_QA_NOTICE_COLOR, qa_notice_color)
    await redis_runtime.set(KEY_QA_NOTICE_FONT_WEIGHT, str(qa_notice_font_weight))
    await redis_runtime.set(KEY_QA_NOTICE_WIDTH, str(qa_notice_width))

    after = RuntimeConfigResponse(
        show_subscribe_button=body.show_subscribe_button,
        free_daily_quota=body.free_daily_quota,
        free_delay_enabled=body.free_delay_enabled,
        free_delay_seconds=body.free_delay_seconds,
        free_delay_notice_text=notice_normalized,
        pro_monthly_quota=body.pro_monthly_quota,
        qa_notice_enabled=body.qa_notice_enabled,
        qa_notice_text=qa_notice_text,
        qa_notice_font_size=qa_notice_font_size,
        qa_notice_color=qa_notice_color,
        qa_notice_font_weight=qa_notice_font_weight,
        qa_notice_width=qa_notice_width,
    )

    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": before.model_dump(),
        "after": after.model_dump(),
    }

    return after


def _clamp_preview_max_count(raw: int) -> int:
    return max(
        INBOX_PREVIEW_MAX_COUNT_MIN,
        min(INBOX_PREVIEW_MAX_COUNT_MAX, raw),
    )


async def get_chat_model(redis_runtime: AsyncRedis) -> str:
    """RAG 본 체인에서 사용할 채팅 모델명 조회.

    Redis 미설정 또는 화이트리스트 위반 시 ``DEFAULT_CHAT_MODEL``(o4-mini)로 폴백.
    fail-safe: 손상된 값이 들어가 있어도 서비스는 인수자 기본값으로 계속 응답.
    """
    raw = await redis_runtime.get(KEY_CHAT_MODEL)
    if raw is None:
        return DEFAULT_CHAT_MODEL
    value = str(raw)
    if value not in ALLOWED_CHAT_MODELS:
        return DEFAULT_CHAT_MODEL
    return value


async def set_chat_model(redis_runtime: AsyncRedis, value: str) -> str:
    """채팅 모델명 저장. 화이트리스트 위반 시 ``ValueError`` raise (라우터에서 400 변환)."""
    if value not in ALLOWED_CHAT_MODELS:
        raise ValueError(
            f"지원하지 않는 모델입니다: {value}. 허용 모델: {', '.join(ALLOWED_CHAT_MODELS)}"
        )
    await redis_runtime.set(KEY_CHAT_MODEL, value)
    return value


async def get_inbox_preview_max_count(redis_runtime: AsyncRedis) -> int:
    raw = await redis_runtime.get(KEY_INBOX_PREVIEW_MAX_COUNT)
    return _clamp_preview_max_count(_to_int(raw, DEFAULT_INBOX_PREVIEW_MAX_COUNT))


async def set_inbox_preview_max_count(
    redis_runtime: AsyncRedis, value: int
) -> int:
    clamped = _clamp_preview_max_count(value)
    await redis_runtime.set(KEY_INBOX_PREVIEW_MAX_COUNT, str(clamped))
    return clamped


# =============================================================================
# Story 5.5 — USD→KRW 환산 환율 (read-only, runtime:usd_to_krw)
# 운영자가 환율 변경 시 redis-cli SET 수동 실행. 편집 UI는 후속 스토리 책임.
# =============================================================================

KEY_USD_TO_KRW = "runtime:usd_to_krw"
# 자동 갱신 메타키 — forex_tasks 가 매일 09:00 KST SET. 관리자 UI 에서 마지막 갱신 시각 표시.
KEY_USD_TO_KRW_UPDATED_AT = "runtime:usd_to_krw_updated_at"
KEY_USD_TO_KRW_SEARCH_DATE = "runtime:usd_to_krw_search_date"
DEFAULT_USD_TO_KRW = 1400
USD_TO_KRW_MIN = 1000
USD_TO_KRW_MAX = 3000


@dataclass(frozen=True)
class UsdKrwSnapshot:
    rate: int
    updated_at: str | None  # ISO8601 UTC, 한 번도 자동 갱신 안 됐으면 None
    search_date: str | None  # YYYY-MM-DD, API 가 실제로 데이터를 반환한 영업일


async def get_usd_to_krw(redis_runtime: AsyncRedis) -> int:
    """USD→KRW 환산 환율 조회. 미설정 또는 sanity(1000~3000) 위반 시 기본 1400."""
    raw = await redis_runtime.get(KEY_USD_TO_KRW)
    if raw is None:
        return DEFAULT_USD_TO_KRW
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_USD_TO_KRW
    if not (USD_TO_KRW_MIN <= v <= USD_TO_KRW_MAX):
        return DEFAULT_USD_TO_KRW
    return v


async def get_usd_to_krw_snapshot(redis_runtime: AsyncRedis) -> UsdKrwSnapshot:
    """환율 + 자동 갱신 메타데이터 묶음 조회 — 관리자 UI 표시용."""
    rate = await get_usd_to_krw(redis_runtime)
    updated_at = await redis_runtime.get(KEY_USD_TO_KRW_UPDATED_AT)
    search_date = await redis_runtime.get(KEY_USD_TO_KRW_SEARCH_DATE)
    return UsdKrwSnapshot(
        rate=rate,
        updated_at=updated_at,
        search_date=search_date,
    )


# =============================================================================
# Story 4.2 — 야간 광고 차단 토글 (F-502, NFR-C5, 협의서 #C-02)
# 관리자 편집 경로(A-305)는 Epic 7 책임 — 본 모듈은 읽기 전용.
# =============================================================================

KEY_NIGHT_AD_BLOCK_ENABLED = "runtime:night_ad_block_enabled"
KEY_NIGHT_BLOCK_ACTIVE = "runtime:night_block_active"
KEY_NIGHT_BLOCK_START_HOUR = "runtime:night_block_start_hour"
KEY_NIGHT_BLOCK_END_HOUR = "runtime:night_block_end_hour"

DEFAULT_NIGHT_AD_BLOCK_ENABLED = True
DEFAULT_NIGHT_BLOCK_START_HOUR = 21
DEFAULT_NIGHT_BLOCK_END_HOUR = 8


@dataclass(frozen=True)
class NightBlockSettings:
    enabled: bool          # 마스터 토글 (관리자 ON/OFF)
    active: bool | None    # Beat가 SET한 현재 상태; None이면 호출자가 시각 기반 폴백


async def get_night_block_settings(redis_runtime: AsyncRedis) -> NightBlockSettings:
    """야간 광고 차단 설정을 조회한다.

    Redis 호출 실패 시 enabled=True(fail-closed) + active=None 반환.
    fail-closed인 이유: 광고성 발송이 야간에 일어나는 것은 정보통신망법 위반 리스크(NFR-C5).
    """
    try:
        enabled_raw = await redis_runtime.get(KEY_NIGHT_AD_BLOCK_ENABLED)
        active_raw = await redis_runtime.get(KEY_NIGHT_BLOCK_ACTIVE)
    except Exception:
        return NightBlockSettings(enabled=True, active=None)
    enabled = _to_bool(enabled_raw, DEFAULT_NIGHT_AD_BLOCK_ENABLED)
    if active_raw is None:
        active = None
    else:
        active = str(active_raw).lower() in ("1", "true", "on", "yes")
    return NightBlockSettings(enabled=enabled, active=active)


# =============================================================================
# 이상 질문 패턴 throttle — '답변 완료 시각 기준 3초 이내 후속 질문 연속 3회'
# 탐지 시 해당 사용자의 답변 출력 속도를 관리자 설정값으로 자동 제한한다.
# qa_service.preflight 가 본 키들을 읽어 sleep 값을 결정한다.
# =============================================================================

KEY_ANOMALY_THROTTLE_ENABLED = "runtime:anomaly_throttle_enabled"
KEY_ANOMALY_THROTTLE_FREE_DELAY = "runtime:anomaly_throttle_free_delay"
KEY_ANOMALY_THROTTLE_PRO_DELAY = "runtime:anomaly_throttle_pro_delay"

DEFAULT_ANOMALY_THROTTLE_ENABLED = True
# 무료/유료 throttle 기본값 — 무료는 더 길게(체감 패널티),
# 유료는 결제자 보호 차원에서 짧게 두되 결제자가 어뷰저면 어쨌든 제한.
DEFAULT_ANOMALY_THROTTLE_FREE_DELAY = Decimal("5.0")
DEFAULT_ANOMALY_THROTTLE_PRO_DELAY = Decimal("2.0")
# Numeric(4,1) 컬럼과 동일한 0.0~999.9 범위로 클램프.
ANOMALY_THROTTLE_DELAY_MIN = Decimal("0.0")
ANOMALY_THROTTLE_DELAY_MAX = Decimal("999.9")


def _to_decimal_seconds(raw: str | None, default: Decimal) -> Decimal:
    """Redis 문자열을 0.1초 정밀도 Decimal 로 변환. 손상 값/None 은 default."""
    if raw is None:
        return default
    try:
        value = Decimal(str(raw)).quantize(Decimal("0.1"))
    except Exception:
        return default
    if value < ANOMALY_THROTTLE_DELAY_MIN:
        return ANOMALY_THROTTLE_DELAY_MIN
    if value > ANOMALY_THROTTLE_DELAY_MAX:
        return ANOMALY_THROTTLE_DELAY_MAX
    return value


async def get_anomaly_throttle_config(
    redis_runtime: AsyncRedis,
) -> AnomalyThrottleConfigResponse:
    """현재 throttle 설정 조회 — 미설정 시 코드 기본값.

    호출자: 관리자 GET 라우터 + qa_service.preflight 의 throttle 적용 분기.
    """
    enabled_raw = await redis_runtime.get(KEY_ANOMALY_THROTTLE_ENABLED)
    free_raw = await redis_runtime.get(KEY_ANOMALY_THROTTLE_FREE_DELAY)
    pro_raw = await redis_runtime.get(KEY_ANOMALY_THROTTLE_PRO_DELAY)

    return AnomalyThrottleConfigResponse(
        enabled=_to_bool(enabled_raw, DEFAULT_ANOMALY_THROTTLE_ENABLED),
        free_delay_seconds=float(
            _to_decimal_seconds(free_raw, DEFAULT_ANOMALY_THROTTLE_FREE_DELAY)
        ),
        pro_delay_seconds=float(
            _to_decimal_seconds(pro_raw, DEFAULT_ANOMALY_THROTTLE_PRO_DELAY)
        ),
    )


async def update_anomaly_throttle_config(
    request: Request,
    body: AnomalyThrottleConfigUpdateRequest,
    redis_runtime: AsyncRedis,
) -> AnomalyThrottleConfigResponse:
    """관리자 PUT — 3 키 일괄 저장. audit diff 는 미들웨어가 INSERT."""
    before = await get_anomaly_throttle_config(redis_runtime)

    free_delay = Decimal(str(body.free_delay_seconds)).quantize(Decimal("0.1"))
    pro_delay = Decimal(str(body.pro_delay_seconds)).quantize(Decimal("0.1"))

    await redis_runtime.set(KEY_ANOMALY_THROTTLE_ENABLED, "true" if body.enabled else "false")
    await redis_runtime.set(KEY_ANOMALY_THROTTLE_FREE_DELAY, str(free_delay))
    await redis_runtime.set(KEY_ANOMALY_THROTTLE_PRO_DELAY, str(pro_delay))

    after = AnomalyThrottleConfigResponse(
        enabled=body.enabled,
        free_delay_seconds=float(free_delay),
        pro_delay_seconds=float(pro_delay),
    )

    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": before.model_dump(),
        "after": after.model_dump(),
    }
    return after


# =============================================================================
# 로그인 실패 이상탐지 기준 횟수 — auth_service.login_user 가 본 키를 읽어
# anomaly_events INSERT + 10분 lockout 트리거 임계로 사용한다.
# 기본 3회. 1~20 사이로 클램프 (1=엄격, 20=느슨).
# =============================================================================

KEY_LOGIN_BRUTE_THRESHOLD = "runtime:login_brute_threshold"

DEFAULT_LOGIN_BRUTE_THRESHOLD = 3
LOGIN_BRUTE_THRESHOLD_MIN = 1
LOGIN_BRUTE_THRESHOLD_MAX = 20


def _clamp_login_brute_threshold(raw: int) -> int:
    return max(
        LOGIN_BRUTE_THRESHOLD_MIN,
        min(LOGIN_BRUTE_THRESHOLD_MAX, raw),
    )


async def get_login_brute_threshold(redis_runtime: AsyncRedis) -> int:
    """현재 임계값 — 미설정/손상 시 코드 기본값으로 폴백.

    호출자: 관리자 GET 라우터 + ``auth_service.login_user`` 의 실패 카운터 비교.
    fail-safe: Redis 가 죽었거나 값이 깨져도 항상 기본 3회로 동작해야 함.
    """
    raw = await redis_runtime.get(KEY_LOGIN_BRUTE_THRESHOLD)
    return _clamp_login_brute_threshold(_to_int(raw, DEFAULT_LOGIN_BRUTE_THRESHOLD))


async def get_login_brute_threshold_config(
    redis_runtime: AsyncRedis,
) -> LoginBruteThresholdConfigResponse:
    """관리자 폼 prefill 용 — 현재값 + bounds 메타 묶음."""
    current = await get_login_brute_threshold(redis_runtime)
    return LoginBruteThresholdConfigResponse(
        threshold=current,
        default_threshold=DEFAULT_LOGIN_BRUTE_THRESHOLD,
        min_threshold=LOGIN_BRUTE_THRESHOLD_MIN,
        max_threshold=LOGIN_BRUTE_THRESHOLD_MAX,
    )


async def update_login_brute_threshold_config(
    request: Request,
    body: LoginBruteThresholdConfigUpdateRequest,
    redis_runtime: AsyncRedis,
) -> LoginBruteThresholdConfigResponse:
    """관리자 PUT — 단일 키 저장. audit diff 는 미들웨어가 INSERT."""
    before = await get_login_brute_threshold(redis_runtime)
    clamped = _clamp_login_brute_threshold(body.threshold)
    await redis_runtime.set(KEY_LOGIN_BRUTE_THRESHOLD, str(clamped))

    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": {"login_brute_threshold": before},
        "after": {"login_brute_threshold": clamped},
    }
    return LoginBruteThresholdConfigResponse(
        threshold=clamped,
        default_threshold=DEFAULT_LOGIN_BRUTE_THRESHOLD,
        min_threshold=LOGIN_BRUTE_THRESHOLD_MIN,
        max_threshold=LOGIN_BRUTE_THRESHOLD_MAX,
    )


async def resolve_anomaly_throttle_delay(
    redis_runtime: AsyncRedis,
    *,
    subscription_status: str,
) -> tuple[Decimal, bool]:
    """preflight 분기용 — throttle 적용 시 사용할 delay 와 활성 여부 반환.

    반환: (delay_seconds, enabled). enabled=False 시 delay=0 으로 호출자가 skip.
    """
    cfg = await get_anomaly_throttle_config(redis_runtime)
    if not cfg.enabled:
        return (Decimal("0"), False)
    if subscription_status == "pro":
        return (Decimal(str(cfg.pro_delay_seconds)).quantize(Decimal("0.1")), True)
    # admin 은 호출자에서 이미 우회됨. free/그 외 status 는 무료 값.
    return (Decimal(str(cfg.free_delay_seconds)).quantize(Decimal("0.1")), True)


# =============================================================================
# 이상탐지 임계값 통합 설정 — 별도 페이지(/admin/anomaly/thresholds)에서
# 6개 카테고리 11개 항목을 한 번에 편집한다. 서버 재배포 없이 즉시 반영.
#
# 각 항목은 Redis 키 + 코드 기본값 + clamp 범위(min/max)로 정의된다. fail-safe:
# Redis 미설정/손상/연결 실패 시 코드 기본값으로 폴백 — 인증/QA 경로가 런타임
# 설정 가용성에 의존하지 않도록 한다.
# =============================================================================

# 1) 비밀번호 반복 실패 — 잠금 시간 (실패 허용 횟수는 위 LOGIN_BRUTE_THRESHOLD 재사용).
KEY_LOGIN_LOCKOUT_SECONDS = "runtime:login_lockout_seconds"
DEFAULT_LOGIN_LOCKOUT_SECONDS = 600         # 10분
LOGIN_LOCKOUT_SECONDS_MIN = 60              # 최소 1분
LOGIN_LOCKOUT_SECONDS_MAX = 86400           # 최대 24시간

# 2) 동일 IP 다중 로그인.
KEY_CONCURRENT_IP_THRESHOLD = "runtime:concurrent_ip_threshold"
DEFAULT_CONCURRENT_IP_THRESHOLD = 3
CONCURRENT_IP_THRESHOLD_MIN = 2
CONCURRENT_IP_THRESHOLD_MAX = 50

KEY_CONCURRENT_IP_WINDOW_SECONDS = "runtime:concurrent_ip_window_seconds"
DEFAULT_CONCURRENT_IP_WINDOW_SECONDS = 600  # 10분
CONCURRENT_IP_WINDOW_SECONDS_MIN = 60
CONCURRENT_IP_WINDOW_SECONDS_MAX = 3600

# 3) 동일 질문 반복.
KEY_REPEATED_QUESTION_THRESHOLD = "runtime:repeated_question_threshold"
DEFAULT_REPEATED_QUESTION_THRESHOLD = 3
REPEATED_QUESTION_THRESHOLD_MIN = 2
REPEATED_QUESTION_THRESHOLD_MAX = 50

# 4) 답변 직후 빠른 후속 질문.
KEY_RAPID_FOLLOWUP_WINDOW_SECONDS = "runtime:rapid_followup_window_seconds"
DEFAULT_RAPID_FOLLOWUP_WINDOW_SECONDS = Decimal("3.0")
RAPID_FOLLOWUP_WINDOW_SECONDS_MIN = Decimal("0.5")
RAPID_FOLLOWUP_WINDOW_SECONDS_MAX = Decimal("60.0")

KEY_RAPID_FOLLOWUP_THRESHOLD = "runtime:rapid_followup_threshold"
DEFAULT_RAPID_FOLLOWUP_THRESHOLD = 3
RAPID_FOLLOWUP_THRESHOLD_MIN = 2
RAPID_FOLLOWUP_THRESHOLD_MAX = 50

# 5) 휴대폰 인증 남용.
KEY_SMS_MAX_RETRIES = "runtime:sms_max_retries"
DEFAULT_SMS_MAX_RETRIES = 5                 # 시간당 발송 허용 (6번째부터 429)
SMS_MAX_RETRIES_MIN = 1
SMS_MAX_RETRIES_MAX = 20

KEY_SMS_ABUSE_THRESHOLD = "runtime:sms_abuse_threshold"
DEFAULT_SMS_ABUSE_THRESHOLD = 10            # 1시간 누적 도달 시 24시간 차단
SMS_ABUSE_THRESHOLD_MIN = 2
SMS_ABUSE_THRESHOLD_MAX = 100

KEY_SMS_MAX_WRONG = "runtime:sms_max_wrong"
DEFAULT_SMS_MAX_WRONG = 3                   # OTP 오답 허용 횟수
SMS_MAX_WRONG_MIN = 1
SMS_MAX_WRONG_MAX = 20

# 6) 비밀번호·아이디 찾기 남용.
KEY_RECOVERY_ABUSE_THRESHOLD = "runtime:recovery_abuse_threshold"
DEFAULT_RECOVERY_ABUSE_THRESHOLD = 4        # 1시간 N회 시도
RECOVERY_ABUSE_THRESHOLD_MIN = 2
RECOVERY_ABUSE_THRESHOLD_MAX = 50


def _clamp_int(raw: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, raw))


def _clamp_decimal(raw: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if raw < lo:
        return lo
    if raw > hi:
        return hi
    return raw


async def _get_clamped_int(
    redis_runtime: AsyncRedis, key: str, default: int, lo: int, hi: int
) -> int:
    raw = await redis_runtime.get(key)
    return _clamp_int(_to_int(raw, default), lo, hi)


async def _get_clamped_decimal(
    redis_runtime: AsyncRedis,
    key: str,
    default: Decimal,
    lo: Decimal,
    hi: Decimal,
) -> Decimal:
    raw = await redis_runtime.get(key)
    return _clamp_decimal(_to_decimal_seconds(raw, default), lo, hi)


# ── 개별 fail-safe getters — 인증/QA 경로에서 직접 호출 ───────────────────────

async def get_login_lockout_seconds(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_LOGIN_LOCKOUT_SECONDS,
        DEFAULT_LOGIN_LOCKOUT_SECONDS,
        LOGIN_LOCKOUT_SECONDS_MIN,
        LOGIN_LOCKOUT_SECONDS_MAX,
    )


async def get_concurrent_ip_threshold(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_CONCURRENT_IP_THRESHOLD,
        DEFAULT_CONCURRENT_IP_THRESHOLD,
        CONCURRENT_IP_THRESHOLD_MIN,
        CONCURRENT_IP_THRESHOLD_MAX,
    )


async def get_concurrent_ip_window_seconds(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_CONCURRENT_IP_WINDOW_SECONDS,
        DEFAULT_CONCURRENT_IP_WINDOW_SECONDS,
        CONCURRENT_IP_WINDOW_SECONDS_MIN,
        CONCURRENT_IP_WINDOW_SECONDS_MAX,
    )


async def get_repeated_question_threshold(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_REPEATED_QUESTION_THRESHOLD,
        DEFAULT_REPEATED_QUESTION_THRESHOLD,
        REPEATED_QUESTION_THRESHOLD_MIN,
        REPEATED_QUESTION_THRESHOLD_MAX,
    )


async def get_rapid_followup_window_seconds(redis_runtime: AsyncRedis) -> Decimal:
    return await _get_clamped_decimal(
        redis_runtime,
        KEY_RAPID_FOLLOWUP_WINDOW_SECONDS,
        DEFAULT_RAPID_FOLLOWUP_WINDOW_SECONDS,
        RAPID_FOLLOWUP_WINDOW_SECONDS_MIN,
        RAPID_FOLLOWUP_WINDOW_SECONDS_MAX,
    )


async def get_rapid_followup_threshold(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_RAPID_FOLLOWUP_THRESHOLD,
        DEFAULT_RAPID_FOLLOWUP_THRESHOLD,
        RAPID_FOLLOWUP_THRESHOLD_MIN,
        RAPID_FOLLOWUP_THRESHOLD_MAX,
    )


async def get_sms_max_retries(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_SMS_MAX_RETRIES,
        DEFAULT_SMS_MAX_RETRIES,
        SMS_MAX_RETRIES_MIN,
        SMS_MAX_RETRIES_MAX,
    )


async def get_sms_abuse_threshold(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_SMS_ABUSE_THRESHOLD,
        DEFAULT_SMS_ABUSE_THRESHOLD,
        SMS_ABUSE_THRESHOLD_MIN,
        SMS_ABUSE_THRESHOLD_MAX,
    )


async def get_sms_max_wrong(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_SMS_MAX_WRONG,
        DEFAULT_SMS_MAX_WRONG,
        SMS_MAX_WRONG_MIN,
        SMS_MAX_WRONG_MAX,
    )


async def get_recovery_abuse_threshold(redis_runtime: AsyncRedis) -> int:
    return await _get_clamped_int(
        redis_runtime,
        KEY_RECOVERY_ABUSE_THRESHOLD,
        DEFAULT_RECOVERY_ABUSE_THRESHOLD,
        RECOVERY_ABUSE_THRESHOLD_MIN,
        RECOVERY_ABUSE_THRESHOLD_MAX,
    )


# ── 묶음 응답/저장 — 관리자 페이지 prefill·일괄 PUT ───────────────────────────

def _int_item(current: int, default: int, lo: int, hi: int) -> AnomalyThresholdsItem:
    return AnomalyThresholdsItem(
        current=float(current),
        default=float(default),
        min=float(lo),
        max=float(hi),
    )


def _dec_item(
    current: Decimal, default: Decimal, lo: Decimal, hi: Decimal
) -> AnomalyThresholdsItem:
    return AnomalyThresholdsItem(
        current=float(current),
        default=float(default),
        min=float(lo),
        max=float(hi),
    )


async def get_anomaly_thresholds_config(
    redis_runtime: AsyncRedis,
) -> AnomalyThresholdsConfigResponse:
    """관리자 페이지 prefill — 11개 항목 + 각 항목 bounds 동봉."""
    return AnomalyThresholdsConfigResponse(
        login_brute_threshold=_int_item(
            await get_login_brute_threshold(redis_runtime),
            DEFAULT_LOGIN_BRUTE_THRESHOLD,
            LOGIN_BRUTE_THRESHOLD_MIN,
            LOGIN_BRUTE_THRESHOLD_MAX,
        ),
        login_lockout_seconds=_int_item(
            await get_login_lockout_seconds(redis_runtime),
            DEFAULT_LOGIN_LOCKOUT_SECONDS,
            LOGIN_LOCKOUT_SECONDS_MIN,
            LOGIN_LOCKOUT_SECONDS_MAX,
        ),
        concurrent_ip_threshold=_int_item(
            await get_concurrent_ip_threshold(redis_runtime),
            DEFAULT_CONCURRENT_IP_THRESHOLD,
            CONCURRENT_IP_THRESHOLD_MIN,
            CONCURRENT_IP_THRESHOLD_MAX,
        ),
        concurrent_ip_window_seconds=_int_item(
            await get_concurrent_ip_window_seconds(redis_runtime),
            DEFAULT_CONCURRENT_IP_WINDOW_SECONDS,
            CONCURRENT_IP_WINDOW_SECONDS_MIN,
            CONCURRENT_IP_WINDOW_SECONDS_MAX,
        ),
        repeated_question_threshold=_int_item(
            await get_repeated_question_threshold(redis_runtime),
            DEFAULT_REPEATED_QUESTION_THRESHOLD,
            REPEATED_QUESTION_THRESHOLD_MIN,
            REPEATED_QUESTION_THRESHOLD_MAX,
        ),
        rapid_followup_window_seconds=_dec_item(
            await get_rapid_followup_window_seconds(redis_runtime),
            DEFAULT_RAPID_FOLLOWUP_WINDOW_SECONDS,
            RAPID_FOLLOWUP_WINDOW_SECONDS_MIN,
            RAPID_FOLLOWUP_WINDOW_SECONDS_MAX,
        ),
        rapid_followup_threshold=_int_item(
            await get_rapid_followup_threshold(redis_runtime),
            DEFAULT_RAPID_FOLLOWUP_THRESHOLD,
            RAPID_FOLLOWUP_THRESHOLD_MIN,
            RAPID_FOLLOWUP_THRESHOLD_MAX,
        ),
        sms_max_retries=_int_item(
            await get_sms_max_retries(redis_runtime),
            DEFAULT_SMS_MAX_RETRIES,
            SMS_MAX_RETRIES_MIN,
            SMS_MAX_RETRIES_MAX,
        ),
        sms_abuse_threshold=_int_item(
            await get_sms_abuse_threshold(redis_runtime),
            DEFAULT_SMS_ABUSE_THRESHOLD,
            SMS_ABUSE_THRESHOLD_MIN,
            SMS_ABUSE_THRESHOLD_MAX,
        ),
        sms_max_wrong=_int_item(
            await get_sms_max_wrong(redis_runtime),
            DEFAULT_SMS_MAX_WRONG,
            SMS_MAX_WRONG_MIN,
            SMS_MAX_WRONG_MAX,
        ),
        recovery_abuse_threshold=_int_item(
            await get_recovery_abuse_threshold(redis_runtime),
            DEFAULT_RECOVERY_ABUSE_THRESHOLD,
            RECOVERY_ABUSE_THRESHOLD_MIN,
            RECOVERY_ABUSE_THRESHOLD_MAX,
        ),
    )


async def update_anomaly_thresholds_config(
    request,
    body: AnomalyThresholdsConfigUpdateRequest,
    redis_runtime: AsyncRedis,
) -> AnomalyThresholdsConfigResponse:
    """11개 항목 일괄 저장. clamp 후 모든 키 SET. audit diff 는 미들웨어가 INSERT."""
    before = await get_anomaly_thresholds_config(redis_runtime)

    # 각 값 clamp 후 SET.
    pairs_int = (
        (
            KEY_LOGIN_BRUTE_THRESHOLD,
            _clamp_int(
                body.login_brute_threshold,
                LOGIN_BRUTE_THRESHOLD_MIN,
                LOGIN_BRUTE_THRESHOLD_MAX,
            ),
        ),
        (
            KEY_LOGIN_LOCKOUT_SECONDS,
            _clamp_int(
                body.login_lockout_seconds,
                LOGIN_LOCKOUT_SECONDS_MIN,
                LOGIN_LOCKOUT_SECONDS_MAX,
            ),
        ),
        (
            KEY_CONCURRENT_IP_THRESHOLD,
            _clamp_int(
                body.concurrent_ip_threshold,
                CONCURRENT_IP_THRESHOLD_MIN,
                CONCURRENT_IP_THRESHOLD_MAX,
            ),
        ),
        (
            KEY_CONCURRENT_IP_WINDOW_SECONDS,
            _clamp_int(
                body.concurrent_ip_window_seconds,
                CONCURRENT_IP_WINDOW_SECONDS_MIN,
                CONCURRENT_IP_WINDOW_SECONDS_MAX,
            ),
        ),
        (
            KEY_REPEATED_QUESTION_THRESHOLD,
            _clamp_int(
                body.repeated_question_threshold,
                REPEATED_QUESTION_THRESHOLD_MIN,
                REPEATED_QUESTION_THRESHOLD_MAX,
            ),
        ),
        (
            KEY_RAPID_FOLLOWUP_THRESHOLD,
            _clamp_int(
                body.rapid_followup_threshold,
                RAPID_FOLLOWUP_THRESHOLD_MIN,
                RAPID_FOLLOWUP_THRESHOLD_MAX,
            ),
        ),
        (
            KEY_SMS_MAX_RETRIES,
            _clamp_int(
                body.sms_max_retries,
                SMS_MAX_RETRIES_MIN,
                SMS_MAX_RETRIES_MAX,
            ),
        ),
        (
            KEY_SMS_ABUSE_THRESHOLD,
            _clamp_int(
                body.sms_abuse_threshold,
                SMS_ABUSE_THRESHOLD_MIN,
                SMS_ABUSE_THRESHOLD_MAX,
            ),
        ),
        (
            KEY_SMS_MAX_WRONG,
            _clamp_int(
                body.sms_max_wrong,
                SMS_MAX_WRONG_MIN,
                SMS_MAX_WRONG_MAX,
            ),
        ),
        (
            KEY_RECOVERY_ABUSE_THRESHOLD,
            _clamp_int(
                body.recovery_abuse_threshold,
                RECOVERY_ABUSE_THRESHOLD_MIN,
                RECOVERY_ABUSE_THRESHOLD_MAX,
            ),
        ),
    )
    for key, value in pairs_int:
        await redis_runtime.set(key, str(value))

    # Decimal 1개 — 0.1 정밀도.
    rapid_window = _clamp_decimal(
        Decimal(str(body.rapid_followup_window_seconds)).quantize(Decimal("0.1")),
        RAPID_FOLLOWUP_WINDOW_SECONDS_MIN,
        RAPID_FOLLOWUP_WINDOW_SECONDS_MAX,
    )
    await redis_runtime.set(KEY_RAPID_FOLLOWUP_WINDOW_SECONDS, str(rapid_window))

    after = await get_anomaly_thresholds_config(redis_runtime)

    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": before.model_dump(),
        "after": after.model_dump(),
    }
    return after

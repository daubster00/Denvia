"""Story 4.6 — 관리자 알림톡 관리 페이지 서비스.

엔드포인트 그룹 `/api/v1/admin/alimtalk/*` 의 비즈니스 로직.

핵심 설계 결정 (스토리 §핵심 설계 결정):
- 테스트 수신 번호 SSOT 1곳 — Redis runtime_config(`alimtalk:test_recipient_phone`).
  클라이언트는 phone 을 body 로 보내지 않는다 (서버측 Redis 만 읽음).
- 평문 phone 은 응답·로그·UI 어디에도 노출 안 함 — `phone_masked` 만.

안전장치 6중 (AC-5):
1. 수신 번호 SSOT 1곳
2. 일일 상한 20건/관리자 (Redis INCR + EXPIRE 86400)
3. 010 정규식 강제 (구번호 011/016 미허용)
4. 마스킹 노출
5. audit_logs 양쪽 기록 (`alimtalk.test_send_dispatched` + `alimtalk.test_recipient_updated`)
6. sub_operator 는 수신 번호 변경 권한 없음 (라우터 가드에서 차단)
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.messaging.admin_catalog import (
    SMS_CATALOG,
    CatalogChannel,
    build_admin_catalog_entries,
    category_sort_key,
    is_sms_template,
    render_body_example,
)
from api.src.integrations.messaging.port import MessagingProvider
from api.src.integrations.messaging.templates import (
    TEMPLATE_CATALOG,
    TemplateCategory,
    TemplateDefinition,
)
from api.src.models.notification_queue import (
    CHANNEL_ALIMTALK,
    CHANNEL_SMS,
    STATUS_FAILED,
    STATUS_SENT,
    NotificationQueue,
)
from api.src.models.user import User
from api.src.services.admin_logs_service import _decode_cursor, _encode_cursor


# 🚫 공지사항 알림톡(category=notice)은 발송 폐기(2026-05-28).
# 카탈로그(`notice.generic`)에 잔존하는 이유는 야간 차단(F-502) 회귀 테스트 fixture
# 단 하나 — 운영 발송 0건, 알리고 매핑 없음. 관리자 알림톡 관리 페이지 어디에도
# 노출 금지 (사용자 재클레임 2026-06-05, [[feedback_no_notice_alimtalk_in_admin_ui]]).
_EXCLUDED_CATEGORIES_FROM_ADMIN_UI: frozenset[TemplateCategory] = frozenset(
    {TemplateCategory.NOTICE}
)


def _is_visible_in_admin_ui(template: TemplateDefinition) -> bool:
    """관리자 알림톡 페이지에 노출할 템플릿인지 — 공지(notice) 제외."""
    return template.category not in _EXCLUDED_CATEGORIES_FROM_ADMIN_UI

logger = structlog.get_logger(__name__)

# ── Redis 키 SSOT ────────────────────────────────────────────────────────
_REDIS_KEY_TEST_RECIPIENT = "alimtalk:test_recipient_phone"
_REDIS_KEY_QUOTA_PREFIX = "alimtalk:test_send_count"
_DAILY_QUOTA = 20

# 010 + 8자리 숫자 강제. 구번호 011/016 등 미허용.
_PHONE_REGEX = re.compile(r"^010\d{8}$")

# 폐기·미발송 템플릿 — 운영 카탈로그에는 노출하지만 카운트/테스트 발송 시 안전 — TEMPLATE_CATALOG 전부 노출.
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 200


# ── 헬퍼 ─────────────────────────────────────────────────────────────────


def _strip_phone(phone: str | None) -> str:
    """하이픈·공백·괄호 제거."""
    return re.sub(r"[\s\-()]", "", phone or "")


def _mask_phone(phone: str | bytes | None) -> str | None:
    """평문 phone 을 마스킹 형식으로 변환.

    - 11자리 010 → `010-****-1234`
    - 그 외 (10자리·12자리·비-010) → `****1234` (마지막 4자리)
    - 4자리 미만 → `****`
    - None / 빈 문자열 → None
    """
    if not phone:
        return None
    if isinstance(phone, bytes):
        try:
            phone = phone.decode()
        except UnicodeDecodeError:
            return None
    stripped = _strip_phone(phone)
    if not stripped:
        return None
    if len(stripped) == 11 and stripped.startswith("010"):
        return f"010-****-{stripped[-4:]}"
    if len(stripped) >= 4:
        return f"****{stripped[-4:]}"
    return "****"


def _kst_today_midnight_utc() -> datetime:
    """오늘 KST 자정의 UTC naive datetime (DB 비교용)."""
    now_utc = datetime.now(timezone.utc)
    kst = now_utc + timedelta(hours=9)
    kst_midnight = kst.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = kst_midnight - timedelta(hours=9)
    return utc_midnight.replace(tzinfo=None)


def _kst_month_start_utc() -> datetime:
    """이번 달 KST 1일 자정의 UTC naive datetime."""
    now_utc = datetime.now(timezone.utc)
    kst = now_utc + timedelta(hours=9)
    kst_month_start = kst.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    utc_month_start = kst_month_start - timedelta(hours=9)
    return utc_month_start.replace(tzinfo=None)


def _build_test_variables(template: TemplateDefinition) -> dict[str, str]:
    """템플릿 변수 자동 채움 (AC-4 step 5).

    매핑 규칙:
    - 키에 `amount` 포함 → `"19,800"`
    - 키에 `at` / `date` / `until` 포함 → `"2026-12-31 23:59"`
    - 키에 `name` 포함 → `"테스트사용자"`
    - 키에 `email` 포함 → `"test@denvia.local"`
    - 그 외 → `"테스트값"`
    """
    result: dict[str, str] = {}
    for var in template.variables:
        key = var.lower()
        if "amount" in key:
            result[var] = "19,800"
        elif any(t in key for t in ("at", "date", "until")):
            result[var] = "2026-12-31 23:59"
        elif "name" in key:
            result[var] = "테스트사용자"
        elif "email" in key:
            result[var] = "test@denvia.local"
        else:
            result[var] = "테스트값"
    return result


# ── GET /summary (AC-2) ──────────────────────────────────────────────────


async def get_summary(db: AsyncSession) -> dict[str, Any]:
    """이번 달 + 오늘 통계를 단일 GROUP BY 쿼리로 집계.

    - WHERE: created_at >= 이번 달 1일 KST + status IN (sent, failed)
    - GROUP BY: template_code, status
    - 인메모리: 오늘 분량은 `SUM(CASE WHEN created_at>=today THEN 1 END)` 로 분리.
    - 카운트 0 인 템플릿도 응답에 포함 (admin_catalog outer join 효과).
    - 🚫 notice 카테고리는 admin_catalog가 자동 제외(feedback_no_notice_alimtalk_in_admin_ui).
    - SMS 가상 템플릿(sms.otp / sms.temp_password)도 같은 응답에 채널 구분과 함께 포함.
    """
    today = _kst_today_midnight_utc()
    month_start = _kst_month_start_utc()

    is_today_expr = case(
        (NotificationQueue.created_at >= today, 1),
        else_=0,
    )

    stmt = (
        select(
            NotificationQueue.template_code,
            NotificationQueue.status,
            func.count(NotificationQueue.id).label("month_cnt"),
            func.sum(is_today_expr).label("today_cnt"),
        )
        .where(
            NotificationQueue.created_at >= month_start,
            NotificationQueue.status.in_([STATUS_SENT, STATUS_FAILED]),
        )
        .group_by(NotificationQueue.template_code, NotificationQueue.status)
    )
    rows = (await db.execute(stmt)).all()

    catalog_entries = build_admin_catalog_entries()
    by_template: dict[str, dict[str, int]] = {
        entry.template_code: {
            "today_sent": 0,
            "today_failed": 0,
            "month_sent": 0,
            "month_failed": 0,
        }
        for entry in catalog_entries
    }
    for row in rows:
        code = row.template_code
        if code not in by_template:
            # 카탈로그에 없는 코드(폐기·구버전·notice) — UI 노출 제외.
            continue
        status_str = row.status
        month_cnt = int(row.month_cnt or 0)
        today_cnt = int(row.today_cnt or 0)
        if status_str == STATUS_SENT:
            by_template[code]["month_sent"] += month_cnt
            by_template[code]["today_sent"] += today_cnt
        elif status_str == STATUS_FAILED:
            by_template[code]["month_failed"] += month_cnt
            by_template[code]["today_failed"] += today_cnt

    templates_out: list[dict[str, Any]] = []
    for entry in catalog_entries:
        counts = by_template[entry.template_code]
        if entry.channel == CatalogChannel.SMS:
            # SMS는 카테고리 분류가 없으므로 채널 그룹 정렬용으로 "sms" 사용.
            category_value = "sms"
        else:
            defn = TEMPLATE_CATALOG[entry.template_code]
            category_value = defn.category.value
        templates_out.append(
            {
                "template_code": entry.template_code,
                "title": entry.title,
                "category": category_value,
                "channel": entry.channel.value,
                "aligo_tpl_code": entry.aligo_tpl_code,
                "recipient_kind": entry.recipient_kind,
                "trigger_situation": entry.trigger_situation,
                "body_example": render_body_example(entry.template_code),
                **counts,
            }
        )

    # 정렬: 알림톡(카테고리 우선) → SMS. 같은 그룹 안에서는 template_code 알파벳.
    def _sort_key(t: dict[str, Any]) -> tuple[int, int, str]:
        channel_priority = 0 if t["channel"] == "alimtalk" else 1
        return (
            channel_priority,
            category_sort_key(t["category"]),
            t["template_code"],
        )

    templates_out.sort(key=_sort_key)

    totals = {
        "today_sent": sum(t["today_sent"] for t in templates_out),
        "today_failed": sum(t["today_failed"] for t in templates_out),
        "month_sent": sum(t["month_sent"] for t in templates_out),
        "month_failed": sum(t["month_failed"] for t in templates_out),
    }
    return {"totals": totals, "templates": templates_out}


# ── GET /logs (AC-3) ─────────────────────────────────────────────────────


async def list_logs(
    db: AsyncSession,
    *,
    template_code: str,
    status: str = "all",
    cursor: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    page: int | None = None,
    per_page: int | None = None,
) -> dict[str, Any]:
    """특정 template_code 의 발송 로그.

    2가지 페이지네이션 모드:
    - page-number(권장): `page`(1-based) + `per_page`(1..100) 지정. 응답에 total/total_pages.
    - cursor(레거시): `cursor` 지정. 응답에 next_cursor만 (total 없음, page/total_pages = None).

    `page`/`per_page` 가 오면 cursor는 무시한다.
    """
    # 페이지 번호 모드 검증
    use_page_mode = page is not None or per_page is not None
    if use_page_mode:
        _page = page if page is not None else 1
        _per_page = per_page if per_page is not None else 20
        if _page < 1:
            raise HTTPException(
                422,
                detail={"code": "INVALID_PAGE", "message": "page must be >= 1"},
            )
        if _per_page < 1 or _per_page > 100:
            raise HTTPException(
                422,
                detail={"code": "INVALID_PER_PAGE", "message": "per_page must be 1..100"},
            )
    else:
        _page = None
        _per_page = None
        if limit < 1 or limit > _MAX_LIMIT:
            raise HTTPException(
                422,
                detail={"code": "INVALID_LIMIT", "message": "limit must be 1..200"},
            )

    base_filter = select(NotificationQueue).where(
        NotificationQueue.template_code == template_code
    )

    if status == "sent":
        base_filter = base_filter.where(NotificationQueue.status == STATUS_SENT)
    elif status == "failed":
        base_filter = base_filter.where(NotificationQueue.status == STATUS_FAILED)
    elif status == "all":
        # sent + failed 만 노출 (queued/deferred/processing 은 운영 의미 없음).
        base_filter = base_filter.where(
            NotificationQueue.status.in_([STATUS_SENT, STATUS_FAILED])
        )
    else:
        raise HTTPException(
            422,
            detail={"code": "INVALID_STATUS", "message": "status must be sent|failed|all"},
        )

    next_cursor: str | None = None
    total: int | None = None
    total_pages: int | None = None

    if use_page_mode:
        # 총 건수 — COUNT(*) 별도 쿼리
        count_stmt = select(func.count()).select_from(base_filter.subquery())
        total = int((await db.execute(count_stmt)).scalar() or 0)
        assert _per_page is not None and _page is not None
        total_pages = max(1, (total + _per_page - 1) // _per_page)
        offset = (_page - 1) * _per_page
        stmt = (
            base_filter.order_by(
                NotificationQueue.created_at.desc(), NotificationQueue.id.desc()
            )
            .offset(offset)
            .limit(_per_page)
        )
        rows = list((await db.execute(stmt)).scalars().all())
    else:
        stmt = base_filter
        if cursor:
            cur_at, cur_id = _decode_cursor(cursor)
            from sqlalchemy import or_ as _or

            stmt = stmt.where(
                _or(
                    NotificationQueue.created_at < cur_at,
                    (NotificationQueue.created_at == cur_at)
                    & (NotificationQueue.id < cur_id),
                )
            )
        stmt = stmt.order_by(
            NotificationQueue.created_at.desc(), NotificationQueue.id.desc()
        ).limit(limit + 1)
        rows = list((await db.execute(stmt)).scalars().all())
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = _encode_cursor(last.created_at, last.id)
            rows = rows[:limit]

    items: list[dict[str, Any]] = []
    for r in rows:
        # phone 평문 노출 금지 — variables 에 receiver/phone 키가 있으면 마스킹.
        # NotificationQueue 모델 자체에 phone 컬럼은 없고, user_id 로 매핑된다.
        # 표시용 마스킹은 variables 에 평문 phone 이 있다면 그것만, 일반적으로는 None.
        phone_raw = None
        if isinstance(r.variables, dict):
            phone_raw = r.variables.get("receiver_phone") or r.variables.get("phone")
        created_at_str = _isoformat_utc(r.created_at)
        sent_at_str = _isoformat_utc(r.sent_at) if r.sent_at else None
        # 운영/테스트 구분 — `dispatch_test_send`가 INSERT하는 row의 idempotency_key는
        # `test:{관리자_user_id}:{epoch_ms}` 형식. 운영 발송 키는 별도 prefix(예:
        # `payment:`, `subscription:`, `admin_signup:`).
        is_test = bool(r.idempotency_key and r.idempotency_key.startswith("test:"))
        items.append(
            {
                "id": r.id,
                "created_at": created_at_str,
                "sent_at": sent_at_str,
                "user_id": r.user_id,
                "phone_masked": _mask_phone(phone_raw),
                "channel": r.channel,
                "status": r.status,
                "attempts": r.attempts,
                "last_error": r.last_error,
                "is_test": is_test,
            }
        )

    return {
        "items": items,
        "next_cursor": next_cursor,
        "total": total,
        "page": _page,
        "per_page": _per_page,
        "total_pages": total_pages,
    }


def _isoformat_utc(dt: datetime) -> str:
    """naive datetime → UTC ISO 문자열."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ── GET/PUT/DELETE /test-recipient (AC-6) ────────────────────────────────


async def get_test_recipient(redis: aioredis.Redis) -> dict[str, Any]:
    raw = await redis.get(_REDIS_KEY_TEST_RECIPIENT)
    masked = _mask_phone(raw)
    return {"phone_masked": masked, "is_set": bool(raw)}


async def set_test_recipient(
    redis: aioredis.Redis,
    actor: User,
    phone: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """수신 번호 등록/변경.

    Returns:
        (response_payload, audit_diff) — 라우터가 request.state.audit_diff 설정.
    """
    stripped = _strip_phone(phone)
    if not _PHONE_REGEX.match(stripped):
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_PHONE_FORMAT",
                "message": "010으로 시작하는 11자리 번호만 등록할 수 있습니다.",
            },
        )

    before_raw = await redis.get(_REDIS_KEY_TEST_RECIPIENT)
    before_masked = _mask_phone(before_raw)

    await redis.set(_REDIS_KEY_TEST_RECIPIENT, stripped)

    after_masked = _mask_phone(stripped)
    audit_diff = {
        "op": "set",
        "before_masked": before_masked,
        "after_masked": after_masked,
    }
    logger.info(
        "admin.alimtalk.recipient_set",
        actor_user_id=actor.id,
        before_masked=before_masked,
        after_masked=after_masked,
    )
    return ({"phone_masked": after_masked, "is_set": True}, audit_diff)


async def clear_test_recipient(
    redis: aioredis.Redis,
    actor: User,
) -> dict[str, Any]:
    """수신 번호 해제.

    Returns:
        audit_diff
    """
    before_raw = await redis.get(_REDIS_KEY_TEST_RECIPIENT)
    before_masked = _mask_phone(before_raw)
    await redis.delete(_REDIS_KEY_TEST_RECIPIENT)
    audit_diff = {
        "op": "clear",
        "before_masked": before_masked,
        "after_masked": None,
    }
    logger.info(
        "admin.alimtalk.recipient_cleared",
        actor_user_id=actor.id,
        before_masked=before_masked,
    )
    return audit_diff


# ── POST /test-send (AC-4, AC-5) ─────────────────────────────────────────


def _quota_key(admin_id: int, yyyymmdd: str) -> str:
    return f"{_REDIS_KEY_QUOTA_PREFIX}:{admin_id}:{yyyymmdd}"


def _kst_yyyymmdd_now() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y%m%d")


async def _assert_quota_not_exceeded(redis_rl: aioredis.Redis, admin_id: int) -> None:
    """일일 상한 20건/관리자 — Redis INCR 카운터.

    초과 시 429 + ALIMTALK_TEST_SEND_QUOTA_EXCEEDED.
    """
    key = _quota_key(admin_id, _kst_yyyymmdd_now())
    raw = await redis_rl.get(key)
    current = int(raw) if raw else 0
    if current >= _DAILY_QUOTA:
        raise HTTPException(
            429,
            detail={
                "code": "ALIMTALK_TEST_SEND_QUOTA_EXCEEDED",
                "message": (
                    f"하루 테스트 발송 한도({_DAILY_QUOTA}건)를 초과했습니다. "
                    "내일 다시 시도해주세요."
                ),
            },
        )


async def _increment_quota(redis_rl: aioredis.Redis, admin_id: int) -> None:
    key = _quota_key(admin_id, _kst_yyyymmdd_now())
    new_count = await redis_rl.incr(key)
    if int(new_count) == 1:
        await redis_rl.expire(key, 86400)


async def dispatch_test_send(
    db: AsyncSession,
    redis_runtime: aioredis.Redis,
    redis_rl: aioredis.Redis,
    provider: MessagingProvider,
    actor: User,
    template_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """테스트 발송 디스패치 — 알림톡 또는 SMS.

    Returns:
        (response_payload, audit_diff)
    """
    # 1. 일일 상한
    await _assert_quota_not_exceeded(redis_rl, actor.id)

    # 2. 템플릿 검증 — 알림톡(TEMPLATE_CATALOG) 또는 SMS(SMS_CATALOG)
    is_sms = is_sms_template(template_code)
    alimtalk_template = TEMPLATE_CATALOG.get(template_code) if not is_sms else None
    sms_template = SMS_CATALOG.get(template_code) if is_sms else None
    if not is_sms and alimtalk_template is None:
        raise HTTPException(
            422,
            detail={
                "code": "ALIMTALK_TEMPLATE_NOT_FOUND",
                "message": "등록되지 않은 템플릿입니다.",
            },
        )
    if not is_sms and alimtalk_template is not None:
        if alimtalk_template.category == TemplateCategory.NOTICE:
            # 🚫 공지 알림톡은 발송 폐기 — 테스트 발송도 거부
            #    (feedback_no_notice_alimtalk_in_admin_ui).
            raise HTTPException(
                422,
                detail={
                    "code": "ALIMTALK_TEMPLATE_DEPRECATED",
                    "message": "공지사항 알림톡은 발송 폐기되어 테스트 발송할 수 없습니다.",
                },
            )

    # 3. 수신 번호 로드 (Redis 직독, body 미신뢰)
    phone_raw = await redis_runtime.get(_REDIS_KEY_TEST_RECIPIENT)
    if isinstance(phone_raw, bytes):
        phone_raw = phone_raw.decode()
    if not phone_raw:
        raise HTTPException(
            422,
            detail={
                "code": "ALIMTALK_TEST_RECIPIENT_NOT_SET",
                "message": "상단에서 테스트 수신 번호를 먼저 등록해주세요.",
            },
        )

    # 4. 발송 분기
    success = False
    code_str = "-1"
    error_message: str | None = None
    message_id: str | None = None
    sent_variables: dict[str, str] = {}
    channel_str = CHANNEL_SMS if is_sms else CHANNEL_ALIMTALK

    try:
        if is_sms and sms_template is not None:
            # SMS는 자유 텍스트 — adapter.send_sms() 직접 호출. 본문은 카탈로그 고정값.
            await provider.send_sms(phone_raw, sms_template.body)
            success = True
            code_str = "SMS_OK"
            sent_variables = {"body_preview": sms_template.body[:40]}
        else:
            assert alimtalk_template is not None  # 위에서 검증됨
            sent_variables = _build_test_variables(alimtalk_template)
            result = await provider.send_alimtalk(
                phone_raw, template_code, sent_variables
            )
            success = bool(result.get("success"))
            code_str = str(
                result.get("provider_response_code", "0" if success else "-1")
            )
            message_id = result.get("message_id")
            if not success:
                error_message = f"알리고 reject (code={code_str})"
    except Exception as exc:
        logger.exception(
            "alimtalk.test_send.adapter_error",
            template_code=template_code,
            channel=channel_str,
            actor_user_id=actor.id,
        )
        raise HTTPException(
            502,
            detail={
                "code": "ALIMTALK_SEND_FAILED",
                "message": str(exc) or "어댑터 호출 실패",
            },
        ) from exc

    # 5. notification_queue INSERT — 통계 카드에 합산
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    idem = f"test:{actor.id}:{int(time.time() * 1000)}"
    nq = NotificationQueue(
        user_id=None,
        template_code=template_code,
        variables=sent_variables,
        channel=channel_str,
        status=STATUS_SENT if success else STATUS_FAILED,
        attempts=1,
        last_error=None if success else error_message,
        idempotency_key=idem,
        created_at=now_naive,
        sent_at=now_naive if success else None,
    )
    db.add(nq)
    await db.commit()

    # 6. audit diff
    phone_masked = _mask_phone(phone_raw)
    audit_diff = {
        "template_code": template_code,
        "channel": channel_str,
        "recipient_phone_masked": phone_masked,
        "result_code": code_str,
        "success": success,
    }

    # 7. 일일 카운터 +1
    await _increment_quota(redis_rl, actor.id)

    logger.info(
        "admin.alimtalk.test_sent",
        actor_user_id=actor.id,
        template_code=template_code,
        channel=channel_str,
        success=success,
        result_code=code_str,
    )

    response_payload = {
        "success": success,
        "template_code": template_code,
        "phone_masked": phone_masked,
        "aligo_response_code": code_str,
        "error_message": error_message,
        "message_id": message_id,
    }
    return response_payload, audit_diff

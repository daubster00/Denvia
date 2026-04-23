"""KST(Asia/Seoul) 시각 헬퍼 — DST 없음, UTC+9 고정 offset 사용 (Story 4.2 규약)."""

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 KST 시각을 반환한다."""
    return datetime.now(KST)


def is_night_block_time() -> bool:
    """야간 광고 차단 시간(21:00~08:00 KST)인지 확인한다.

    Story 4.2의 Celery Beat(`runtime:night_block_active` Redis 키)이 없을 때도
    현재 시각 기반으로 판정하는 이중 안전망으로 동작한다.
    """
    hour = now_kst().hour
    return hour >= 21 or hour < 8


def next_8am_kst() -> datetime:
    """다음 08:00 KST 시각을 반환한다 (야간 deferred 항목의 발송 예약 시각)."""
    now = now_kst()
    today_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now < today_8am:
        return today_8am
    return today_8am + timedelta(days=1)

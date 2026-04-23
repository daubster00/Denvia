"""notification_queue SQLAlchemy ORM 모델 — 알림 발송 큐 및 감사 기록."""

from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

# channel 값 상수
CHANNEL_ALIMTALK = "alimtalk"
CHANNEL_SMS = "sms"

# status 값 상수
STATUS_QUEUED = "queued"             # 발송 대기 (Epic 3 billing 이벤트 등)
STATUS_PROCESSING = "processing"     # dispatch 태스크가 처리 중 (중복 claim 방지)
STATUS_SENT = "sent"                 # 발송 성공
STATUS_FAILED = "failed"             # 모든 시도 실패 (감사 기록)
STATUS_DEFERRED = "deferred"         # 야간 차단으로 지연 예약
STATUS_RATE_LIMITED = "rate_limited_deferred"  # 레이트 리밋 초과 지연


class NotificationQueue(Base):
    """알림 발송 큐 — 지연·실패·대기 항목을 보관하고 Celery 태스크가 처리한다."""

    __tablename__ = "notification_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 논리적 FK: users.id (활성 사용자 없어도 기록 유지를 위해 FK 제약 없음)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    template_code: Mapped[str] = mapped_column(String(100), nullable=False)
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # 'alimtalk' | 'sms'
    channel: Mapped[str] = mapped_column(String(20), nullable=False)

    # 'queued' | 'sent' | 'failed' | 'deferred' | 'rate_limited_deferred'
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_QUEUED)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 멱등성 키 — UNIQUE(user_id, template_code, idempotency_key)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)

    # 야간 차단·레이트 리밋 지연 시 설정; NULL이면 즉시 처리 가능
    deferred_until: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)

"""PaymentEvent SQLAlchemy ORM 모델 — Story 3.1 결제 이벤트 로그 테이블."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "charge_requested",
            "charge_success",
            "charge_failed",
            "retry_scheduled",
            "refund_requested",
            "refund_success",
            "refund_denied",
            name="payment_event_type_enum",
        ),
        nullable=False,
    )
    # PG 응답 원본 — 디버깅·감사 목적으로 보관 (평문 빌링키 절대 포함 금지)
    raw_response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

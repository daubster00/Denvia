"""Refund SQLAlchemy ORM 모델 — Story 9.1 v1.1 관리자 운영 환불(부분/전액).

ADR-0001 편차 #5 환불 정책 v1.1. 동일 결제 건에 대해 다회 부분환불을 시계열로 보존.
`refund_sequence`는 동일 결제 내 1부터 증가하며, `idempotency_key`는
`refund:{payment_id}:manual:{refund_sequence}` 패턴으로 알림톡·재시도 멱등성 보장.

마이그레이션: `0031_refunds`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    payment_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    cancel_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    original_payment_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    prorated_suggestion: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reason_category: Mapped[str] = mapped_column(
        Enum(
            "customer_complaint",
            "duplicate_payment",
            "system_error",
            "special_mid_cancel",
            "other",
            name="refund_reason_category_enum",
            create_type=False,
        ),
        nullable=False,
    )

    memo: Mapped[str | None] = mapped_column(Text, nullable=True)

    refund_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    toss_response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

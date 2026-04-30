"""Payment SQLAlchemy ORM 모델 — Story 3.1 결제 내역 테이블."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(
        Enum("toss", "nicepay", name="pg_provider_enum"), nullable=False
    )
    provider_order_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    amount_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "success",
            "failed",
            "refunded",
            "refund_pending",
            name="payment_status_enum",
        ),
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="1", default=1
    )
    charged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Story 3.4: 예약된 retry Celery task ID — 카드 변경 시 revoke 대상
    retry_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Story 4.4 코드리뷰 후속: 결제 당시 회차 스냅샷.
    # Subscription.current_period_end는 자동 갱신 시 미래로 이동하므로 과거 결제 row의
    # "구독 기간" 표시가 오염되는 것을 막기 위해 결제 생성 시점 값을 그대로 박제한다.
    subscription_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

# DEPRECATED v1.1 (ADR-0001 편차 #5, 2026-05-13) — 신규 환불 row는 refunds 테이블에 INSERT.
# 본 모델·테이블은 폐지된 자가 환불 폼 → 관리자 큐 흐름의 잔여물이다. 신규 환불 INSERT는
# api.src.models.refund.Refund + api.src.services.admin_payment_service.create_refund 사용.
# 본 모델·DB 테이블의 실제 제거는 Phase 3에서 결정한다(잔여 row 0건 확인 후 alembic drop).
"""ManualRefundQueue SQLAlchemy ORM 모델 — Story 3.6 수동 환불 검토 큐 — [DEPRECATED v1.1].

자동 환불 조건(7일 이내 + qa_logs=0건) 미충족 시 INSERT.
Epic 9 A-503 관리자 화면에서 status='approved'/'denied'로 UPDATE.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class ManualRefundQueue(Base):
    __tablename__ = "manual_refund_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    qa_count_during_period: Mapped[int] = mapped_column(Integer, nullable=False)
    days_since_charge: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "approved",
            "denied",
            name="manual_refund_queue_status_enum",
        ),
        nullable=False,
        server_default="pending",
    )
    reviewer_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

"""BudgetThreshold ORM — Story 5.2 월 예산 임계 추적."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CHAR, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class BudgetThreshold(Base):
    __tablename__ = "budget_thresholds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    year_month: Mapped[str] = mapped_column(CHAR(7), nullable=False, unique=True)
    monthly_limit_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    warning_80_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    warning_95_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    killswitch_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

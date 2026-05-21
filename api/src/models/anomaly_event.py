"""AnomalyEvent SQLAlchemy ORM 모델."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Enum, ForeignKey, JSON, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

_AnomalyType = Enum(
    "login_brute_force",
    "concurrent_ip_login",
    "repeated_question",
    "recovery_abuse",
    "rapid_followup_questions",
    name="anomaly_event_type",
    create_constraint=False,
)

_AnomalyStatus = Enum(
    "new",
    "reviewed",
    "actioned",
    "unblocked",
    name="anomaly_event_status",
    create_constraint=False,
)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(_AnomalyType, nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(_AnomalyStatus, nullable=False, default="new")
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

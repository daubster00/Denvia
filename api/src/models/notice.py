"""공지(알림글) ORM — Story 4.5 DDL, Story 7.1 admin CRUD 책임."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum as SQLEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    target_segment: Mapped[str] = mapped_column(
        SQLEnum(
            "all",
            "doctor",
            "hygienist",
            "student_other",
            name="segment_target_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="all",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

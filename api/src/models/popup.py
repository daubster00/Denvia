"""팝업 ORM — Story 4.5 DDL, Story 7.2 admin CRUD 책임.

본 스토리는 SELECT만 사용 (GET /me/popups/active).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class Popup(Base):
    __tablename__ = "popups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    display_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
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
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="TRUE"
    )
    created_by_admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("display_start < display_end", name="ck_popups_display_window"),
    )

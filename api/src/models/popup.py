"""팝업 ORM — Story 4.5(DDL) + 7.2 v2 재설계.

target_device: 노출 디바이스 (pc/mobile/both)
popup_type   : 'image'(한 장 이미지) 또는 'editor'(Tiptap 본문)
image_url    : popup_type='image' 일 때 사용
sort_order   : 캐러셀 내 노출 순서 (작은 값 먼저)

CHECK ck_popups_type_payload: 타입별 페이로드 일치 보장.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
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
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    target_device: Mapped[str] = mapped_column(
        SQLEnum(
            "pc",
            "mobile",
            "both",
            name="popup_target_device_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="both",
    )
    popup_type: Mapped[str] = mapped_column(
        SQLEnum(
            "image",
            "editor",
            name="popup_type_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="editor",
    )
    display_position: Mapped[str] = mapped_column(
        SQLEnum(
            "center",
            "top",
            "bottom",
            "bottom_left",
            "bottom_right",
            name="popup_display_position_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="center",
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="TRUE"
    )
    created_by_admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("display_start < display_end", name="ck_popups_display_window"),
        CheckConstraint(
            "(popup_type = 'image' AND image_url IS NOT NULL) "
            "OR (popup_type = 'editor' AND body_html IS NOT NULL)",
            name="ck_popups_type_payload",
        ),
    )

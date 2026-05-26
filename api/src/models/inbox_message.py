"""쪽지함 메시지 ORM — Story 4.5 + admin_dm 확장(0051).

발행 시점의 title/body_html 스냅샷을 보존(notice 수정/삭제와 무관하게 사용자 이력 유지).
notice 경로: type='notice'|'system'|'billing' / popup 경로: type='notice'.
admin_dm 경로(관리자 → 특정 사용자 1:1): notice_id NULL + popup_id NULL +
created_by_admin_id 채움.
직접 INSERT(billing 알림 등): notice_id NULL + popup_id NULL.

partial UNIQUE: (user_id, popup_id) WHERE popup_id IS NOT NULL — 팝업당 1행 보장.

deleted_at: 사용자가 쪽지함에서 삭제하면 채워진다. 30일 후 retention 배치가
영구 삭제한다. 조회/카운트는 항상 deleted_at IS NULL 조건을 포함해야 한다.
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


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    notice_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("notices.id", ondelete="CASCADE"), nullable=True
    )
    popup_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("popups.id", ondelete="CASCADE"), nullable=True
    )
    inquiry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("customer_inquiries.id", ondelete="SET NULL"),
        nullable=True,
    )
    reply_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("inquiry_replies.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        SQLEnum(
            "notice",
            "system",
            "billing",
            "admin_dm",
            name="inbox_message_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="FALSE"
    )
    seen_popup_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "(notice_id IS NOT NULL AND popup_id IS NULL AND type IN ('notice','system','billing')) "
            "OR (popup_id IS NOT NULL AND notice_id IS NULL AND type = 'notice') "
            "OR (notice_id IS NULL AND popup_id IS NULL AND type IN ('system','billing','admin_dm'))",
            name="ck_inbox_source_type",
        ),
    )

"""고객 문의 ORM — Story 4.5 사용자 submit, Story 9.3 admin 답변 책임.

0030: 1:1 문의 게시판화 — inquiry_type 컬럼 추가.
body는 plain text(html.escape 적용 후 저장). 이미지 첨부는 inquiry_attachments에 분리 저장.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class CustomerInquiry(Base):
    __tablename__ = "customer_inquiries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    inquiry_type: Mapped[str] = mapped_column(
        SQLEnum(
            "billing",
            "account",
            "usage",
            "bug",
            "suggestion",
            "other",
            name="inquiry_type_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="other",
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "open",
            "in_progress",
            "resolved",
            name="inquiry_status_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="open",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

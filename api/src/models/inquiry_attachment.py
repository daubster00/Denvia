"""InquiryAttachment ORM — 0030 CS 1:1 문의 게시판화.

사용자가 문의 작성 시 첨부한 이미지(jpg/png/webp). 문의 1건당 최대 5장.
파일은 api/data/uploads/inquiries/ 에 uuid prefix로 저장되고,
file_url은 /static/inquiry-images/<uuid>.<ext> 형식.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class InquiryAttachment(Base):
    __tablename__ = "inquiry_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inquiry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("customer_inquiries.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

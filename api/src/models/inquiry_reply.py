"""InquiryReply ORM — Story 9.3 관리자 답변 이력.

customer_inquiries(4.5) 1건당 N건 답변 이력 보존. reply_html은 nh3 sanitize 후 저장.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class InquiryReply(Base):
    __tablename__ = "inquiry_replies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inquiry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("customer_inquiries.id", ondelete="CASCADE"),
        nullable=False,
    )
    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reply_html: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

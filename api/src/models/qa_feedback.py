"""QAFeedback SQLAlchemy ORM 모델 — Story 2.1 질의 피드백 테이블.

reviewed_at NULL = 미검토 / NOT NULL = 검토완료 (migration 0062).
원본 rating(good/bad)은 그대로 보존하고 검토 상태는 별도 컬럼으로 표현한다.
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class QAFeedback(Base):
    __tablename__ = "qa_feedback"
    __table_args__ = (CheckConstraint("rating IN ('good', 'bad')", name="ck_qa_feedback_rating"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    qa_log_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("qa_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[str] = mapped_column(String(4), nullable=False)
    change_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )

"""QAReview SQLAlchemy ORM 모델 — #113 질의응답 검토(굿/베드 + 코멘트) 테이블.

기존 qa_feedback(고객 피드백)과는 완전히 분리된 별도 개념이다.
운영진(sub_operator)이 질문+답변을 검토해 굿/베드를 누르고 베드에는 코멘트를 달며,
최고관리자(master/operator)가 '검토완료'를 처리한다.

- qa_log_id 당 1행(UNIQUE).
- rating NULL = 미평가 / 'good' / 'bad'.
- reviewed_at NULL = 미검토 / NOT NULL = 검토완료.
- hidden_at NOT NULL = 다중삭제 소프트플래그(목록에서 숨김).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class QAReview(Base):
    __tablename__ = "qa_reviews"
    __table_args__ = (
        UniqueConstraint("qa_log_id", name="uq_qa_reviews_qa_log_id"),
        CheckConstraint(
            "rating IS NULL OR rating IN ('good', 'bad')",
            name="ck_qa_reviews_rating",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    qa_log_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("qa_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL = 미평가 / 'good' / 'bad'
    rating: Mapped[str | None] = mapped_column(String(4), nullable=True, default=None)
    # 'bad' 일 때만 채워지는 검토 코멘트
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 굿/베드를 누른 관리자
    rated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # 평가 변경 누적 횟수(굿↔베드 전환·해제 포함)
    change_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0", default=0
    )
    # NULL = 미검토 / NOT NULL = 검토완료(처리 시각)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # 다중삭제 소프트플래그: NOT NULL 이면 목록에서 숨김
    hidden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
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

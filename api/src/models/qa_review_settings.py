"""QAReviewSettings SQLAlchemy ORM 모델 — #113 질의응답 검토 단일행 설정.

id=1 단일 행만 존재하는 config 테이블.
sub_operator(부관리자)가 조회할 수 있는 최대 과거 일수를 담는다.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class QAReviewSettings(Base):
    __tablename__ = "qa_review_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_qa_review_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    # 부관리자(sub_operator)가 조회 가능한 최대 과거 일수
    sub_operator_max_lookback_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="7", default=7
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

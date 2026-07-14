"""QAReviewAdminSetting ORM 모델 — #132 부관리자별 질의응답 검토 조회 설정.

전역 단일 설정(QAReviewSettings)과 별개로, 초대된 부관리자(제한 등급) 각각에게
독립적인 조회기간(max_lookback_days)과 강제 평가필터(rating_scope)를 부여한다.
행이 없으면 전역 기본값 + 필터 'all'(제한 없음)로 폴백한다.
"""
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class QAReviewAdminSetting(Base):
    __tablename__ = "qa_review_admin_settings"
    __table_args__ = (
        UniqueConstraint("admin_id", name="uq_qa_review_admin_settings_admin_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # None → 전역 기본값(sub_operator_max_lookback_days) 사용.
    max_lookback_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 이 부관리자가 볼 수 있는 평가 필터(강제). 'all'|'good'|'bad'|'unrated'.
    #   all 이 아니면 목록이 해당 평가만 보이도록 강제된다(예: unrated = 미평가만).
    rating_scope: Mapped[str] = mapped_column(String(10), nullable=False, default="all")
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default="NOW()")

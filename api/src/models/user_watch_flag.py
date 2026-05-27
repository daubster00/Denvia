"""UserWatchFlag — 이상탐지 "주의 계정" 플래그.

이상탐지 리스트의 별 모양 버튼으로 관리자가 특정 계정을 주의 계정으로 등록한다.
user_id UNIQUE — 한 사용자당 한 행.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class UserWatchFlag(Base):
    __tablename__ = "user_watch_flags"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_watch_flags_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    flagged_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_anomaly_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("anomaly_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    anomaly_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

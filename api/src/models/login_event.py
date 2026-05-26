"""LoginEvent SQLAlchemy ORM 모델 — 로그인 성공 이벤트 1건 = 1행.

관리자 대시보드 "접속 통계" (일/주/월/년 접속자 수 + 접속횟수) 기반 데이터.
- 적재: 패스워드 / OAuth 로그인 성공 시점 (auth_service / routers.auth)
- 집계: api.src.services.access_analytics_service
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)
    # password | oauth_google | oauth_kakao | oauth_naver — 디버깅·향후 분리집계용.
    method: Mapped[str] = mapped_column(Text, nullable=False, default="password")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

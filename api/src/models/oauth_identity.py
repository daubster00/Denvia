"""OAuthIdentity SQLAlchemy ORM 모델 — Story 1.6 소셜 로그인 식별자 테이블."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class OAuthIdentity(Base):
    __tablename__ = "oauth_identity"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(10), nullable=False)
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(tz=timezone.utc),
    )

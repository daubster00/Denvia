"""User SQLAlchemy ORM 모델."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="user")
    subscription_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="free"
    )
    segment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    years_of_experience: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_reset_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    daily_quota_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_delay_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

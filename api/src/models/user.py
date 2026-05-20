"""User SQLAlchemy ORM 모델."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Integer, Numeric, SmallInteger, String, Text
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
    # 회원정보 — 마이페이지 회원정보 수정에서 사용. 모두 nullable(기존 가입자 호환).
    name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address_road: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_detail: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 인구통계 — 마이페이지 선택 입력. 'male'|'female'|NULL.
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    birthdate: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 마케팅 활용 동의 — 알림톡·SMS·이메일 통합 단일 동의.
    # NULL = 미동의(또는 한 번도 동의한 적 없음). timestamp = 마지막 동의 시각.
    # 철회 시 marketing_consent_at = NULL, marketing_withdrawn_at = now (이력 보존).
    marketing_consent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    marketing_withdrawn_at: Mapped[datetime | None] = mapped_column(nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_reset_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    daily_quota_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_delay_override: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 1), nullable=True
    )
    # Story 6.2 — 권한·차단 컬럼
    blocked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 차단 전 subscription_status 보존 — 만료/해제 시 복원에 사용 (Story 6.2 fix)
    pre_block_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pro_granted_by_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

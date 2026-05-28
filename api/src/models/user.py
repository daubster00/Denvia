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
    # 매년 1월 1일 00:05 KST 배치(career_tasks.annual_increment)가 +1 누적할 때 갱신.
    # 같은 KST 연도에 두 번 실행돼도 멱등하도록 가드값으로 사용.
    experience_last_increment_year: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
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
    # 이상 질문 패턴(연속 3회 3초 이내 후속 질문) 탐지 시 자동 throttle 시각.
    # NULL = throttle 미적용. 관리자가 수동 해제할 때까지 지속.
    anomaly_throttled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    pro_granted_by_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # 단일 세션(later wins) — 로그인 시점에 nonce를 발급하고 JWT의 sid 클레임과 매칭한다.
    # 새 로그인이 일어나면 값이 갱신돼 이전 쿠키의 sid는 자동으로 mismatch → 401.
    current_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Story 10.1 — 다중 관리자 + 등급 RBAC (ADR-0001 편차 #6)
    # role=='admin'인 행만 의미를 가진다. role=='user'는 NULL.
    # 내장: 'master'|'operator'|'sub_operator'|'pending'. 0057 이후 커스텀 등급 코드도 가능.
    # admin_grades.code 와 FK (ON UPDATE CASCADE, ON DELETE RESTRICT).
    # master 는 partial UNIQUE 인덱스(WHERE admin_grade='master' AND withdrawn_at IS NULL)로 단일성 강제.
    admin_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    admin_blocked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    admin_block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_signup_at: Mapped[datetime | None] = mapped_column(nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

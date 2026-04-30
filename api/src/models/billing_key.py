"""BillingKey SQLAlchemy ORM 모델 — Story 3.1 빌링키 저장 테이블."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class BillingKey(Base):
    __tablename__ = "billing_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(
        Enum("toss", "nicepay", name="pg_provider_enum"), nullable=False
    )
    # Fernet 암호화된 빌링키 바이트 — 평문은 서비스 레이어 외부에 노출 금지 (AR21, NFR-S2)
    billing_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # 토스 자동결제 승인 양쪽에 필요 — API 응답·로그 노출 금지 (Story 3.2)
    customer_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_company: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

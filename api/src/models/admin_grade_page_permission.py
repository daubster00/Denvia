"""AdminGradePagePermission — 등급(operator·sub_operator) × 페이지 접근 권한.

Story 10.5 — Epic 10 / ADR-0001 편차 #6 후속(등급 단위 운영).
0055_admin_grade_page_permissions 마이그레이션과 1:1 매핑.

매트릭스(FR61 갱신판):
- master      : 본 테이블 무관 — 항상 모든 페이지 접근 가능
- operator    : 본 테이블에서 (admin_grade='operator', page_route) allowed=true 인 페이지
- sub_operator: 본 테이블에서 (admin_grade='sub_operator', page_route) allowed=true 인 페이지
- pending     : 로그인 단계(get_current_admin)에서 차단됨
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class AdminGradePagePermission(Base):
    __tablename__ = "admin_grade_page_permissions"
    __table_args__ = (
        UniqueConstraint(
            "admin_grade",
            "page_route",
            name="uq_admin_grade_page_permissions",
        ),
        CheckConstraint(
            "admin_grade IN ('operator','sub_operator')",
            name="ck_admin_grade_page_permissions_grade",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_grade: Mapped[str] = mapped_column(
        PGEnum(
            "master",
            "operator",
            "sub_operator",
            "pending",
            name="admin_grade_enum",
            create_type=False,
        ),
        nullable=False,
    )
    page_route: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

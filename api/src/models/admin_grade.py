"""AdminGrade — 관리자 등급 메타(SSOT).

0057 마이그레이션에서 도입. 기존 ENUM(master/operator/sub_operator/pending) 을
VARCHAR + 본 테이블로 전환해 운영자가 커스텀 등급을 추가/삭제할 수 있게 한다.

- is_builtin=true 4종(master/operator/sub_operator/pending) : 삭제·라벨 변경 금지
- is_builtin=false : 운영자가 추가한 커스텀 등급. label 입력 → 코드는 서비스에서 g_<hex> 자동.
- 커스텀 등급의 권한은 admin_grade_page_permissions 매트릭스로 페이지별 ON/OFF.
  서비스가 등급 추가 시 기본 OFF 9행을 자동 시드한다.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class AdminGrade(Base):
    __tablename__ = "admin_grades"
    __table_args__ = (UniqueConstraint("label", name="uq_admin_grades_label"),)

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
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

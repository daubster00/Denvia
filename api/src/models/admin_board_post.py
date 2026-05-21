"""AdminBoardPost ORM — 관리자 수정요청 게시판 글.

마이그레이션 0040_admin_board + 0041_board_status_completed 와 1:1 매핑.
status: review(요청사항검토) | in_progress(수정중) | rejected(수정불가) | on_hold(보류) | completed(수정완료).
category: 앱 레벨에서 검증 (api/src/services/admin_board_service.py: ALLOWED_CATEGORIES).
content_html: sanitize_body_html() 적용 후 저장.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class AdminBoardPost(Base):
    __tablename__ = "admin_board_posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "review",
            "in_progress",
            "rejected",
            "on_hold",
            "completed",
            name="board_post_status_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="review",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

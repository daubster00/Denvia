"""AdminBoardAttachment ORM — 관리자 수정요청 게시판 글 첨부파일.

마이그레이션 0064_board_feature_dev 와 1:1 매핑.
글 1건당 첨부 여러 개(문서/압축/이미지). post 삭제 시 CASCADE.
파일은 api/data/uploads/admin_board_attachments/ 에 uuid prefix로 저장되고,
file_url 은 /static/admin-board-attachments/<uuid>.<ext> 형식.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class AdminBoardAttachment(Base):
    __tablename__ = "admin_board_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admin_board_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

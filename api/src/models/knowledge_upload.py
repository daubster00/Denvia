"""KnowledgeUpload SQLAlchemy ORM 모델 — Story 8.1."""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, desc
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

# status 값 상수 — PostgreSQL ENUM 대신 VARCHAR(20) + 앱 레벨 상수 (에픽 8.2/8.3 값 추가 시 마이그레이션 비용 회피)
STATUS_VALIDATED = "validated"
STATUS_REBUILD_PENDING = "rebuild_pending"
STATUS_ACTIVE = "active"
STATUS_DELETED = "deleted"


class KnowledgeUpload(Base):
    __tablename__ = "knowledge_uploads"
    __table_args__ = (
        Index("idx_knowledge_uploads_content_hash", "content_hash"),
        Index("idx_knowledge_uploads_status_uploaded_at", "status", desc("uploaded_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hierarchy_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    uploaded_by_admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default="NOW()",
    )
    last_modified_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default="NOW()",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

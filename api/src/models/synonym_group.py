"""SynonymGroup ORM 모델 — Story 8.5 동의어 사전 DB SSOT."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class SynonymGroup(Base):
    __tablename__ = "synonym_groups"
    __table_args__ = (
        UniqueConstraint("canonical_term", name="uq_synonym_groups_canonical_term"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_term: Mapped[str] = mapped_column(String(100), nullable=False)
    synonyms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SynonymGroup id={self.id} term={self.canonical_term!r}>"

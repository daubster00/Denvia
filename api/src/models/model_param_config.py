"""ModelParamConfig ORM 모델 — Story 8.4 모델 파라미터 외부화."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

PARAM_KEYS = ("rag_k", "rag_temperature", "max_tokens")


class ModelParamConfig(Base):
    __tablename__ = "model_param_configs"
    __table_args__ = (UniqueConstraint("key", name="uq_model_param_configs_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(30), nullable=False)
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default="NOW()")

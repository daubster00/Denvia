"""PromptModuleConfig ORM 모델 — Story 8.4 런타임 프롬프트 외부화."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

BLOCK_IDS = ("BASE", "치식_위치", "치면_방향", "마취_산정", "브릿지")


class PromptModuleConfig(Base):
    __tablename__ = "prompt_module_configs"
    __table_args__ = (UniqueConstraint("block_id", name="uq_prompt_module_configs_block_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default="NOW()")

"""PromptModuleConfig ORM 모델 — Story 8.4 런타임 프롬프트 외부화."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

# #129: 프롬프트 모듈 10개 전부를 관리자 웹에서 직접 편집(글 내용 + 발동조건).
# seed 순서 = vendor PROMPT_MODULES 등장 순서 (프롬프트 조립 순서 보존용).
BLOCK_IDS = (
    "BASE",
    "치식_위치",
    "치면_방향",
    "마취_산정",
    "브릿지",
    "치주치료_산정",
    "치주낭측정검사_횟수산정",
    "초진,재진",
    "보험레진_와동분류",
    "임플란트_치근면처치술",
)


class PromptModuleConfig(Base):
    __tablename__ = "prompt_module_configs"
    __table_args__ = (UniqueConstraint("block_id", name="uq_prompt_module_configs_block_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 발동조건(트리거 키워드) — 매칭 4종을 담는 JSON.
    #   {"mode":"base"}
    #   {"mode":"keywords","keywords":[...]}
    #   {"mode":"keywords_all","keywords_all":[...]}
    #   {"mode":"keywords_combo","set1":[...],"independent":[...]}
    #   {"mode":"group","group_keywords":[...],"required_keywords":[...]}
    trigger_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default="NOW()")

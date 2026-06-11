"""QALog SQLAlchemy ORM 모델 — Story 2.1 질의응답 기록 테이블."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base


class QALog(Base):
    __tablename__ = "qa_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_matched: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    # Story 2.5: 스트림 완료 상태 — NULL = 레거시 행
    # Python default: 'in_progress' (INSERT 시점)
    # 서버 default: 없음 (nullable)
    status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="in_progress"
    )
    # 관리자 감사용 (Story: QA 상세보기) — SSE 응답에 절대 노출되지 않음
    normalized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_docs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # LLM 에 실제로 들어간 최종 프롬프트(템플릿 + 질문 + top-k 컨텍스트 치환 완료).
    # on_llm_start 콜백이 받는 prompts[0] 그대로. 관리자 감사 전용.
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )

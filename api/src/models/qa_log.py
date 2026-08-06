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
    # #141 진단용 — 접속 기기 종류('mobile'/'pc'/'unknown'). 요청 시작 시 User-Agent 로
    # 판별해 INSERT 하므로, 연결 끊김으로 유령이 된(status=error) 행에도 남는다.
    device_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Story 2.5: 스트림 완료 상태 — NULL = 레거시 행
    # Python default: 'in_progress' (INSERT 시점)
    # 서버 default: 없음 (nullable)
    status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="in_progress"
    )
    # #141 — 완성 답변이 사용자에게 전송 완료됐는지. 백그라운드 스레드가 끝까지 만든
    # 답변은 연결이 끊겨도 저장(completed, delivered=False)되고, 재시도 시 차감 없이
    # 재생된다. 정상 전송 완료 시 True 로 마킹된다.
    delivered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
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

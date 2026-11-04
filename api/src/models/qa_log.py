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
    # #149 검수 P0-2·P1-7 — 답변의 종류. NULL = 일반 RAG/룰 답변.
    # 'clarification' = 조각 질문에 "조금만 더 적어주세요" 로 되묻은 응답.
    # 이전 대화를 서버 로그에서 다시 읽을 때 되묻기 턴을 **구조적으로** 제외하기 위한 값.
    # (문구 문자열 비교로 제외하면 문구를 고치는 순간 과거 턴이 맥락으로 되살아난다)
    answer_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # #149 검수 P0-1 — 이 답변을 만들 때 쓴 "검증된 이전 대화"의 지문(해시).
    # NULL = 이전 대화 없이 만든 답변. 전송 실패 답변 재생(#141)은 질문 문자열뿐 아니라
    # 이 값까지 같을 때만 허용한다 — 다른 대화의 같은 조각 질문에 오재생되던 결함 차단.
    history_context_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # #149 재검수 P1-1 — 저장 답변 재생의 원자적 선점(claim).
    # replay_claimed_at: 재생 권한을 가져간 시각. 조건부 UPDATE 로 NULL → now() 를
    #   성공시킨 요청 **하나만** 재생한다. 리스(기본 30초)가 지나면 다시 가져갈 수 있다.
    # replay_claim_token: 그 선점의 소유자 표식. 연결이 끊겨 선점을 풀 때 자기 것만 푼다.
    replay_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replay_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 관리자 감사용 (Story: QA 상세보기) — SSE 응답에 절대 노출되지 않음
    # #149 검수 P1-4 — 대화 이어가기에서는 **실제로 검색에 쓴 질의**(이전 대화를 반영해
    # 완성한 질문의 정규화 결과)를 저장한다. 사용자 원문은 question_text 에 그대로 있다.
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

"""#149 검수 P0-1·P0-2·P1-7 — 서버가 소유하는 대화 맥락 식별 컬럼 2개.

배경(검수 문서 `docs/CODE_REVIEW_149_2026-11-03.md`):

- P0-2: 이전 대화를 브라우저가 보낸 문자열로 받으면 조작된 과거 답변이 프롬프트에
  그대로 들어간다. 요청은 ``qa_log_id`` 목록만 받고 서버가 자기 로그에서 질문·답변을
  다시 읽어 쓰도록 바꿨다. 그러면 "되묻기 턴" 같은 특수 답변을 **DB 에서** 식별해
  맥락에서 빼야 한다 → ``answer_kind``.
- P1-7: 되묻기 턴 제외를 고정 문구 문자열 비교로 하면 문구를 한 글자만 바꿔도 과거
  턴이 일반 대화로 되살아난다. 구조화된 종류 값으로 고정한다.
- P0-1: 전송 실패 답변 재생(#141)이 질문 문자열만 비교해, 다른 대화 맥락의 같은
  조각 질문("몇 번까지 돼?")에 엉뚱한 답변을 재생했다. 재생 후보에 **그 답변을 만들 때
  쓴 대화 맥락**을 함께 기록해 맥락이 같을 때만 재생한다 → ``history_context_key``.

두 컬럼 모두 additive · nullable. 기존 행은 NULL = "일반 답변 / 맥락 없음" 으로 읽히며,
기존 재생 동작(첫 질문처럼 맥락 없는 요청)과 그대로 호환된다.

- answer_kind: NULL=일반 RAG·룰 답변 / 'clarification'=조각 질문 되묻기 응답
- history_context_key: NULL=이전 대화 없이 생성된 답변 /
  그 외=서버가 검증한 이전 대화 턴 id 목록의 해시(hex 32자)
"""
import sqlalchemy as sa
from alembic import op

revision = "0075_qa_history_trust"
down_revision = "0074_rebuild_job_embedding_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_logs",
        sa.Column("answer_kind", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "qa_logs",
        sa.Column("history_context_key", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("qa_logs", "history_context_key")
    op.drop_column("qa_logs", "answer_kind")

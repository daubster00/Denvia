"""qa_logs에 관리자 감사용 prompt_text 컬럼 추가.

질문 상세 패널에서 "LLM에 실제로 들어간 최종 프롬프트"(템플릿 + 질문 +
top-k 컨텍스트가 모두 채워진 텍스트)를 관리자에게 보여주기 위함.
on_llm_start 콜백으로 LangChain RetrievalQA가 LLM에 보낸 prompt 문자열을
그대로 보관한다. SSE 응답이나 사용자 노출에는 절대 쓰이지 않는 감사 전용 컬럼.

nullable — 기존 행은 NULL로 남고, 본 마이그레이션 이후 신규 질의부터 채워진다.

Revision ID: 0063_qa_log_prompt_text
Revises: 0062_qa_feedback_reviewed
"""

from alembic import op


revision = "0063_qa_log_prompt_text"
down_revision = "0062_qa_feedback_reviewed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE qa_logs ADD COLUMN IF NOT EXISTS prompt_text TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE qa_logs DROP COLUMN IF EXISTS prompt_text")

"""qa_logs에 관리자 감사용 normalized_query, retrieved_docs 컬럼 추가.

관리자 페이지(사용자 상세 → 질의 탭 → 상세보기)에서 RAG 처리 내부 단계를
검증할 수 있도록 다음 두 컬럼을 추가한다.

- normalized_query : 동의어 치환(apply_scaling_rules + normalize_query) 적용 후
                     실제 retriever / rule 엔진에 전달된 최종 쿼리 텍스트.
- retrieved_docs   : top-k 검색에 들어온 문서들의 메타 (list[dict]).
                     각 dict는 {"page_content": str, "metadata": dict} 형태로
                     LangChain Document 직렬화를 따른다.

두 컬럼 모두 nullable — 기존 행은 NULL로 남고, 본 마이그레이션 적용 이후
신규 질의부터 채워진다. SSE 응답에는 절대 노출되지 않으며 관리자 감사 용도
한정 저장이다 (ADR-0002 보강 단서).

Revision ID: 0038_qa_log_audit_fields
Revises: 0037_user_profile_fields
"""

from alembic import op

revision = "0038_qa_log_audit_fields"
down_revision = "0037_user_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE qa_logs ADD COLUMN IF NOT EXISTS normalized_query TEXT")
    op.execute("ALTER TABLE qa_logs ADD COLUMN IF NOT EXISTS retrieved_docs JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE qa_logs DROP COLUMN IF EXISTS retrieved_docs")
    op.execute("ALTER TABLE qa_logs DROP COLUMN IF EXISTS normalized_query")

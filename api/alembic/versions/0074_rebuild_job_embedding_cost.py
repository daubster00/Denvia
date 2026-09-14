"""#145 rebuild_jobs 임베딩 비용 — 지식 재구축 1회의 토큰 수·비용(USD).

배경: 관리자 화면 지출은 qa_logs(챗봇 질의응답)만 합산했다. 비용 집계가
langchain get_openai_callback() 기반이라 채팅(LLM) 호출만 세고 임베딩
(OpenAIEmbeddings) 호출은 세지 않아, 인덱스 재구축 비용이 어디에도 기록되지
않았다(고객 체감 차액의 원인).

- embedding_token_count: 그 재구축에서 임베딩된 총 토큰 수 (tiktoken 로컬 계산)
- embedding_cost_usd   : 위 토큰 수 × text-embedding-3-large 단가($0.13/1M)

additive — nullable. 과거 재구축은 실제 토큰 수를 알 수 없으므로 NULL 로 남긴다
(추측값 백필 금지). 집계 SQL 은 SUM 이 NULL 을 자동 제외한다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0074_rebuild_job_embedding_cost"
down_revision = "0073_qa_delivered"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rebuild_jobs",
        sa.Column("embedding_token_count", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "rebuild_jobs",
        sa.Column("embedding_cost_usd", sa.Numeric(12, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rebuild_jobs", "embedding_cost_usd")
    op.drop_column("rebuild_jobs", "embedding_token_count")

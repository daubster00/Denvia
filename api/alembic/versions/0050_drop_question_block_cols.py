"""users.question_blocked_until / question_block_reason DROP.

차단 방식을 전체 계정 차단(subscription_status='blocked') 하나로 통일 (2026-05-22).
질문 전용 차단 분기는 코드와 함께 컬럼도 제거한다.

down_revision='0049_user_current_session_id'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_drop_question_block_cols"
down_revision = "0049_user_current_session_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_question_blocked_until")
    op.drop_column("users", "question_block_reason")
    op.drop_column("users", "question_blocked_until")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("question_blocked_until", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("question_block_reason", sa.Text(), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_question_blocked_until "
        "ON users (question_blocked_until) "
        "WHERE question_blocked_until IS NOT NULL"
    )

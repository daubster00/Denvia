"""anomaly_events.admin_memo + users.question_blocked_until / question_block_reason 추가.

관리자 이상탐지 페이지 개편 (2026-05-22):
  - anomaly_events.admin_memo      : 관리자가 이벤트별로 남기는 자유 메모 (TEXT NULL).
  - users.question_blocked_until   : 질문(Q&A)만 차단하는 시각. NULL=차단 없음.
                                     로그인 이상(login_brute_force / concurrent_ip_login)
                                     외 분류에서 관리자가 차단하면 전체 계정 대신
                                     이 컬럼만 채워 Q&A 만 막는다.
  - users.question_block_reason    : 위 차단의 사유 (TEXT NULL).
  - idx_users_question_blocked_until : partial BTREE (NULL 제외).

down_revision='0047_drop_rapid_questions'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_anomaly_drawer_cols"
down_revision = "0047_drop_rapid_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "anomaly_events",
        sa.Column("admin_memo", sa.Text(), nullable=True),
    )

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


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_question_blocked_until")
    op.drop_column("users", "question_block_reason")
    op.drop_column("users", "question_blocked_until")
    op.drop_column("anomaly_events", "admin_memo")

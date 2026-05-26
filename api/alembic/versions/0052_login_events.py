"""login_events — 로그인 성공 이벤트 적재 테이블.

배경:
- 관리자 대시보드에 "일/주/월/년 접속자 수 + 접속횟수"를 보여주기 위해 필요.
- 기존 users.last_login_at 은 마지막 1건만 보관해서 히스토리 집계 불가.
- 패스워드 + OAuth 로그인 성공 시점에 1행 적재.

집계 패턴(access_analytics_service):
- 접속자 수(unique visitors) = COUNT(DISTINCT user_id)  per bucket
- 접속횟수(total visits)     = COUNT(*)                  per bucket

down_revision='0051_inbox_admin_dm'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0052_login_events"
down_revision = "0051_inbox_admin_dm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("ua", sa.Text(), nullable=True),
        sa.Column(
            "method",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'password'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
    )

    # 시계열 집계 — KST 일별 GROUP BY 가 핵심. created_at 단독 인덱스가 가장 효과적.
    op.create_index(
        "idx_login_events_created_at",
        "login_events",
        ["created_at"],
    )
    # 사용자별 최근 로그인 조회용.
    op.create_index(
        "idx_login_events_user_created",
        "login_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_login_events_user_created", table_name="login_events")
    op.drop_index("idx_login_events_created_at", table_name="login_events")
    op.drop_table("login_events")

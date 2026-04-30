"""budget_thresholds + killswitch_states — Story 5.2 예산 모니터링 + auto kill-switch."""

import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision = "0012_budget_and_killswitch"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # budget_thresholds
    op.create_table(
        "budget_thresholds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("year_month", sa.CHAR(7), nullable=False),
        sa.Column("monthly_limit_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("warning_80_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warning_95_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("killswitch_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("year_month", name="idx_budget_thresholds_year_month"),
    )

    # killswitch_states
    op.create_table(
        "killswitch_states",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["activated_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "mode IN ('auto_free_only', 'manual_total')",
            name="ck_killswitch_states_mode",
        ),
    )
    op.execute(
        "CREATE INDEX idx_killswitch_active ON killswitch_states (mode) "
        "WHERE deactivated_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_killswitch_active_mode ON killswitch_states (mode) "
        "WHERE deactivated_at IS NULL"
    )

    # 당월 기본 행 INSERT (KST 기준)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    year_month = now_kst.strftime("%Y-%m")
    initial_limit = Decimal(
        os.environ.get("DENVIA_INITIAL_MONTHLY_BUDGET_USD", "100.00")
    )
    op.execute(
        sa.text(
            "INSERT INTO budget_thresholds (year_month, monthly_limit_usd) "
            "VALUES (:ym, :limit)"
        ).bindparams(ym=year_month, limit=initial_limit)
    )

    # NFR-P5 보강: qa_logs 집계 인덱스
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_logs_created_at_user_id "
        "ON qa_logs (created_at, user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_qa_logs_created_at_user_id")
    op.execute("DROP INDEX IF EXISTS uq_killswitch_active_mode")
    op.execute("DROP INDEX IF EXISTS idx_killswitch_active")
    op.drop_table("killswitch_states")
    op.drop_table("budget_thresholds")

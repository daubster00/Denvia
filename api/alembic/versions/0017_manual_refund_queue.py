"""Create manual_refund_queue for Story 3.6 manual refund review.

자동 환불 조건 미충족(7일 초과 또는 구독 기간 내 사용 이력 존재) 시 관리자 수동 검토 큐로
INSERT한다. Epic 9 A-503에서 status='approved'/'denied'로 UPDATE.

partial UNIQUE index(uq_manual_refund_queue_payment_pending)로 동일 payment에 동시 pending
1건만 허용 — 이중 환불 요청 방어.

Revision ID: 0017_manual_refund_queue
Revises: 0016_next_charge_nullable
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017_manual_refund_queue"
down_revision = "0016_next_charge_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_enum = postgresql.ENUM(
        "pending",
        "approved",
        "denied",
        name="manual_refund_queue_status_enum",
        create_type=True,
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "manual_refund_queue",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("qa_count_during_period", sa.Integer(), nullable=False),
        sa.Column("days_since_charge", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="manual_refund_queue_status_enum", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "idx_manual_refund_queue_status",
        "manual_refund_queue",
        ["status", "requested_at"],
    )
    op.create_index(
        "idx_manual_refund_queue_user_id",
        "manual_refund_queue",
        ["user_id"],
    )
    # 동일 payment에 동시 pending 1건만 허용. Alembic autogenerate 미인식 → raw SQL.
    op.execute(
        "CREATE UNIQUE INDEX uq_manual_refund_queue_payment_pending "
        "ON manual_refund_queue (payment_id) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_manual_refund_queue_payment_pending")
    op.drop_index("idx_manual_refund_queue_user_id", table_name="manual_refund_queue")
    op.drop_index("idx_manual_refund_queue_status", table_name="manual_refund_queue")
    op.drop_table("manual_refund_queue")
    op.execute("DROP TYPE IF EXISTS manual_refund_queue_status_enum")

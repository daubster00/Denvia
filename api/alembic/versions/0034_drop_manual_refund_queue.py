"""Drop manual_refund_queue — Story 3.6 v1.1 Phase 4 Step 4.

v1.0 자가 환불 폼(`manual_refund_queue` 승인 큐 기반)을 ADR-0001 편차 #5에 따라 v1.1
운영 환불(관리자가 결제 건당 금액 입력)로 대체하며 백엔드·프론트 dead code는 Phase 4
Step 1/2(commit 970de94, 4112da1)에서 모두 제거됨. 남아 있던 `manual_refund_queue` 테이블
과 `manual_refund_queue_status_enum` 타입을 본 스키마에서 영구 삭제한다.

downgrade는 0017과 동일 스키마(테이블·2개 일반 인덱스·partial unique 인덱스·enum)를
재생성해 롤백 시 데이터 보존은 못 하더라도 구조는 복구되도록 한다.

Revision ID: 0034_drop_manual_refund_queue
Revises: 0033_inbox_reply_link
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0034_drop_manual_refund_queue"
down_revision = "0033_inbox_reply_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_manual_refund_queue_payment_pending")
    op.drop_index("idx_manual_refund_queue_status", table_name="manual_refund_queue")
    op.drop_index("idx_manual_refund_queue_user_id", table_name="manual_refund_queue")
    op.drop_table("manual_refund_queue")
    op.execute("DROP TYPE IF EXISTS manual_refund_queue_status_enum")


def downgrade() -> None:
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
    op.execute(
        "CREATE UNIQUE INDEX uq_manual_refund_queue_payment_pending "
        "ON manual_refund_queue (payment_id) WHERE status = 'pending'"
    )

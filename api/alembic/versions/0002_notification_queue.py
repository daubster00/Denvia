"""notification_queue 테이블 생성 — 알림 발송 큐·감사 기록 (Story 4.1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_queue",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("template_code", sa.String(100), nullable=False),
        sa.Column("variables", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("deferred_until", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # user_id 조회 성능용 인덱스
    op.create_index("idx_notification_queue_user_id", "notification_queue", ["user_id"])

    # 발송 처리 대상 조회 (status + deferred_until)
    op.create_index(
        "idx_notification_queue_status_deferred",
        "notification_queue",
        ["status", "deferred_until"],
    )

    # 멱등성 UNIQUE 제약 — 동일 (user_id, template_code, idempotency_key) 중복 차단
    op.execute(
        """
        CREATE UNIQUE INDEX uq_notification_queue_idempotency
        ON notification_queue(user_id, template_code, idempotency_key)
        WHERE user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("notification_queue")

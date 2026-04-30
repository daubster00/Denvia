"""payments.retry_task_id 추가 — Story 3.4 결제 실패 재시도 태스크 ID 저장."""

import sqlalchemy as sa

from alembic import op

revision = "0015_payment_retry_task_id"
down_revision = "0014_billing_customer_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("retry_task_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "retry_task_id")

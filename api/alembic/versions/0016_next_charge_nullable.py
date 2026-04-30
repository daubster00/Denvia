"""subscriptions.next_charge_at NULLABLE 변경 — Story 3.5 finalize 시 NULL 설정.

`canceled` 상태에서는 `next_charge_at`이 의미상 무의미하므로 NULL 허용.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_next_charge_nullable"
down_revision = "0015_payment_retry_task_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "subscriptions",
        "next_charge_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    # 다운그레이드 시 NULL 행이 있으면 실패 — 운영 롤백 시 사전 정리 필요
    op.alter_column(
        "subscriptions",
        "next_charge_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

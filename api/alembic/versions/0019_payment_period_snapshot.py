"""payments.subscription_period_start/end 스냅샷 컬럼 추가 — Story 4.4 코드리뷰 후속.

자동 갱신 시 Subscription.current_period_end가 미래로 갱신되어, /me/payments
응답이 과거 결제 row까지 모두 "최초 시작일 ~ 최신 만료일"처럼 노출되는 문제를
회피하기 위해 결제 시점의 회차 기간을 payments 행에 snapshot한다.

backfill 정책:
- charged_at IS NOT NULL인 기존 행은 charged_at 기준 30일 회차로 추정 backfill.
- charged_at IS NULL(pending/failed before charge)은 그대로 NULL.
NOTE: backfill은 근사치이며, 신규 행부터는 billing_service가 정확한 회차를 기록한다.
"""

import sqlalchemy as sa

from alembic import op

revision = "0019_payment_period_snapshot"
down_revision = "0018_inbox_and_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column(
            "subscription_period_start",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "subscription_period_end",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 기존 행 backfill — charged_at 기준 30일 회차로 근사 (정책상 신규부터 정확)
    op.execute(
        """
        UPDATE payments
        SET subscription_period_start = charged_at,
            subscription_period_end = charged_at + INTERVAL '30 days'
        WHERE charged_at IS NOT NULL
          AND subscription_period_start IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("payments", "subscription_period_end")
    op.drop_column("payments", "subscription_period_start")

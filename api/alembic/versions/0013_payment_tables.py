"""subscriptions · billing_keys · payments · payment_events — Story 3.1 결제 4테이블."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_payment_tables"
down_revision = "0012_budget_and_killswitch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "cancel_pending",
                "canceled",
                "refund_pending",
                name="subscription_status_enum",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("next_charge_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_subscriptions_user_id", "subscriptions", ["user_id"])

    # billing_keys
    op.create_table(
        "billing_keys",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("toss", "nicepay", name="pg_provider_enum"),
            nullable=False,
        ),
        sa.Column("billing_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("card_company", sa.String(30), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_billing_keys_user_id", "billing_keys", ["user_id"])

    # payments
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "provider",
            sa.Enum("toss", "nicepay", name="pg_provider_enum"),
            nullable=False,
        ),
        sa.Column("provider_order_id", sa.String(), nullable=False),
        sa.Column("amount_krw", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "success",
                "failed",
                "refunded",
                "refund_pending",
                name="payment_status_enum",
            ),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("charged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("provider_order_id", name="uq_payments_provider_order_id"),
    )
    op.create_index("idx_payments_user_id", "payments", ["user_id"])

    # payment_events
    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "charge_requested",
                "charge_success",
                "charge_failed",
                "retry_scheduled",
                "refund_requested",
                "refund_success",
                "refund_denied",
                name="payment_event_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("raw_response_json", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_payment_events_payment_id", "payment_events", ["payment_id"])


def downgrade() -> None:
    op.drop_index("idx_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("idx_payments_user_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("idx_billing_keys_user_id", table_name="billing_keys")
    op.drop_table("billing_keys")

    op.drop_index("idx_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.execute("DROP TYPE IF EXISTS payment_event_type_enum")
    op.execute("DROP TYPE IF EXISTS payment_status_enum")
    op.execute("DROP TYPE IF EXISTS pg_provider_enum")
    op.execute("DROP TYPE IF EXISTS subscription_status_enum")

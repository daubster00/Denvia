"""billing_keys.customer_key 추가 — Story 3.2 Toss 자동결제 customerKey 저장."""

from alembic import op
import sqlalchemy as sa

revision = "0014_billing_customer_key"
down_revision = "0013_payment_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_keys",
        sa.Column("customer_key", sa.String(length=300), nullable=True),
    )
    op.create_index("idx_billing_keys_customer_key", "billing_keys", ["customer_key"])


def downgrade() -> None:
    op.drop_index("idx_billing_keys_customer_key", table_name="billing_keys")
    op.drop_column("billing_keys", "customer_key")

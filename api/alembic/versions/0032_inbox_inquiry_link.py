"""inbox_messages.inquiry_id — 문의 답변 쪽지에서 원본 문의로 연결.

쪽지함에서 "고객문의 답변이 도착했습니다" 카드를 누르면 쪽지 본문 팝업 대신
원본 문의 상세(/my/inquiries/{id})로 이동시키기 위한 연결 컬럼.

기존 답변 쪽지(이전에 발행된 row)는 inquiry_id=NULL로 남으며, 그 경우 웹은
기존처럼 쪽지 본문 팝업을 보여준다 (호환 처리).

down_revision='0031_refunds'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_inbox_inquiry_link"
down_revision = "0031_refunds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_messages",
        sa.Column(
            "inquiry_id",
            sa.BigInteger,
            sa.ForeignKey("customer_inquiries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_inbox_messages_inquiry_id",
        "inbox_messages",
        ["inquiry_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_inbox_messages_inquiry_id", table_name="inbox_messages")
    op.drop_column("inbox_messages", "inquiry_id")

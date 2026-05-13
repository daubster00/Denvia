"""inbox_messages.reply_id — 답변 쪽지 ↔ inquiry_replies 직접 연결.

관리자가 답변을 수정/삭제할 때 사용자 쪽지함도 일치시키기 위한 직결 FK.
신규 답변 등록 시 reply_id를 채우고, 수정/삭제 시 이 컬럼으로 매칭한다.

ondelete='SET NULL' — inquiry_replies row가 사라져도 inbox row는 보존(이력),
서비스 로직에서 inbox row도 함께 삭제 처리한다.

down_revision='0032_inbox_inquiry_link'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_inbox_reply_link"
down_revision = "0032_inbox_inquiry_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_messages",
        sa.Column(
            "reply_id",
            sa.BigInteger,
            sa.ForeignKey("inquiry_replies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_inbox_messages_reply_id",
        "inbox_messages",
        ["reply_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_inbox_messages_reply_id", table_name="inbox_messages")
    op.drop_column("inbox_messages", "reply_id")

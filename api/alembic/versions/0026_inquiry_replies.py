"""Story 9.3 — customer_inquiries 답변 이력 테이블.

본 마이그레이션은 관리자가 Tiptap RichTextEditor로 작성한 sanitize된 reply_html을
다회 보존하기 위한 별도 테이블 `inquiry_replies`를 추가한다.

- ON DELETE CASCADE(inquiry_id): 문의 삭제 시 답변 이력도 함께 제거 (4.5 customer_inquiries 사용자 CASCADE 정책 답습)
- ON DELETE RESTRICT(admin_id): 관리자 계정 직접 삭제 차단 (6.5 audit_logs 패턴 답습)
- idx_inquiry_replies_inquiry_id : (inquiry_id, created_at ASC) — 상세 Drawer 답변 이력 시간순 조회

CONCURRENTLY 미적용 사유: 0020/0025 패턴 일관 + 본 테이블은 신규 생성이라 데이터 0건이므로
인덱스 생성도 즉시. IF NOT EXISTS 가드는 멱등성 보장.

down_revision='0025_payment_events_admin_idx'.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_inquiry_replies"
down_revision = "0025_payment_events_admin_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inquiry_replies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("inquiry_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("reply_html", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inquiry_id"],
            ["customer_inquiries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inquiry_replies_inquiry_id "
        "ON inquiry_replies (inquiry_id, created_at ASC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_inquiry_replies_inquiry_id")
    op.drop_table("inquiry_replies")

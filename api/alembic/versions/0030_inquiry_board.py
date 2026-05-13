"""CS 1:1 문의 게시판화 — inquiry_type 컬럼 + inquiry_attachments 테이블.

기존 customer_inquiries(0018)는 user_id/subject/body/status/created_at/resolved_at만
보유한 단일 폼 구조였다. 본 마이그레이션은 다음을 추가한다.

1) inquiry_type_enum: billing / account / usage / bug / suggestion / other (6종)
   - customer_inquiries.inquiry_type NOT NULL DEFAULT 'other'
     (기존 row 보존을 위해 server_default='other')

2) inquiry_attachments: 사용자가 업로드한 이미지(jpg/png/webp, 최대 5장/문의) 보존
   - id BIGSERIAL PK
   - inquiry_id BIGINT FK→customer_inquiries.id ON DELETE CASCADE
   - file_url VARCHAR(500) NOT NULL   (예: /static/inquiry-images/<uuid>.png)
   - file_name VARCHAR(255) NOT NULL   (원본 파일명; 사용자에게 표시용)
   - mime_type VARCHAR(64) NOT NULL
   - size_bytes BIGINT NOT NULL
   - created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   - idx (inquiry_id, id) — 상세 조회 시 정렬

down_revision='0029_synonym_groups'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_inquiry_board"
down_revision = "0029_synonym_groups"
branch_labels = None
depends_on = None


_INQUIRY_TYPES = ("billing", "account", "usage", "bug", "suggestion", "other")


def upgrade() -> None:
    inquiry_type_enum = postgresql.ENUM(
        *_INQUIRY_TYPES,
        name="inquiry_type_enum",
        create_type=True,
    )
    inquiry_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "customer_inquiries",
        sa.Column(
            "inquiry_type",
            postgresql.ENUM(name="inquiry_type_enum", create_type=False),
            nullable=False,
            server_default="other",
        ),
    )

    op.create_table(
        "inquiry_attachments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("inquiry_id", sa.BigInteger(), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
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
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inquiry_attachments_inquiry "
        "ON inquiry_attachments (inquiry_id, id ASC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_inquiry_attachments_inquiry")
    op.drop_table("inquiry_attachments")

    op.drop_column("customer_inquiries", "inquiry_type")
    op.execute("DROP TYPE IF EXISTS inquiry_type_enum")

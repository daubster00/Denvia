"""knowledge_uploads 테이블 신설 — Story 8.1 (A-401) TXT 지식 업로드.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_uploads",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("category_count", sa.Integer(), nullable=True),
        sa.Column("hierarchy_json", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "uploaded_by_admin_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_modified_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_knowledge_uploads_content_hash",
        "knowledge_uploads",
        ["content_hash"],
    )
    op.create_index(
        "idx_knowledge_uploads_status_uploaded_at",
        "knowledge_uploads",
        ["status", sa.text("uploaded_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_uploads_status_uploaded_at", table_name="knowledge_uploads")
    op.drop_index("idx_knowledge_uploads_content_hash", table_name="knowledge_uploads")
    op.drop_table("knowledge_uploads")

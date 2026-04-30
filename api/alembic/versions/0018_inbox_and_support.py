"""Story 4.5 — 받은 쪽지함 + 고객문의 (F-503 / F-504).

4 테이블 신규:
- notices: 관리자 발행 공지 (Story 7.1 admin CRUD 책임, 본 스토리는 DDL만)
- popups: 메인 진입 팝업 (Story 7.2 admin CRUD 책임)
- inbox_messages: 사용자 쪽지함 (notice/popup 발행 시 bulk INSERT — 7.1/7.2,
  본 스토리는 popup seen 시 UPSERT 1건 + read mark)
- customer_inquiries: 고객 문의 (본 스토리에서 사용자 submit, Story 9.3 admin 답변)

ENUM 4종(중복 회피 위해 segment_target_enum은 popups가 재사용):
- segment_target_enum: 'all' | 'doctor' | 'hygienist' | 'student_other'
- inbox_message_type_enum: 'notice' | 'system' | 'billing'
- inquiry_status_enum: 'open' | 'in_progress' | 'resolved'

partial UNIQUE: uniq_inbox_user_popup ON (user_id, popup_id) WHERE popup_id IS NOT NULL
  → 팝업당 사용자 1행 보장 (idempotent UPSERT 보호).

Revision ID: 0018_inbox_and_support
Revises: 0017_manual_refund_queue
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018_inbox_and_support"
down_revision = "0017_manual_refund_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    segment_enum = postgresql.ENUM(
        "all",
        "doctor",
        "hygienist",
        "student_other",
        name="segment_target_enum",
        create_type=True,
    )
    segment_enum.create(op.get_bind(), checkfirst=True)

    inbox_type_enum = postgresql.ENUM(
        "notice",
        "system",
        "billing",
        name="inbox_message_type_enum",
        create_type=True,
    )
    inbox_type_enum.create(op.get_bind(), checkfirst=True)

    inquiry_status_enum = postgresql.ENUM(
        "open",
        "in_progress",
        "resolved",
        name="inquiry_status_enum",
        create_type=True,
    )
    inquiry_status_enum.create(op.get_bind(), checkfirst=True)

    # ── notices ──────────────────────────────────────────────────────────────
    op.create_table(
        "notices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column(
            "target_segment",
            postgresql.ENUM(name="segment_target_enum", create_type=False),
            nullable=False,
            server_default="all",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"], ["users.id"], ondelete="RESTRICT"
        ),
    )
    op.execute(
        "CREATE INDEX idx_notices_published_segment "
        "ON notices (published_at, target_segment) "
        "WHERE published_at IS NOT NULL"
    )

    # ── popups ───────────────────────────────────────────────────────────────
    op.create_table(
        "popups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("display_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("display_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "target_segment",
            postgresql.ENUM(name="segment_target_enum", create_type=False),
            nullable=False,
            server_default="all",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "display_start < display_end", name="ck_popups_display_window"
        ),
    )
    op.create_index(
        "idx_popups_active_window",
        "popups",
        ["is_active", "display_start", "display_end"],
    )

    # ── inbox_messages ──────────────────────────────────────────────────────
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("notice_id", sa.BigInteger(), nullable=True),
        sa.Column("popup_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "type",
            postgresql.ENUM(name="inbox_message_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("seen_popup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["popup_id"], ["popups.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(notice_id IS NOT NULL AND popup_id IS NULL AND type IN ('notice','system','billing')) "
            "OR (popup_id IS NOT NULL AND notice_id IS NULL AND type = 'notice') "
            "OR (notice_id IS NULL AND popup_id IS NULL AND type IN ('system','billing'))",
            name="ck_inbox_source_type",
        ),
    )
    op.execute(
        "CREATE INDEX idx_inbox_user_unread "
        "ON inbox_messages (user_id, is_read, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_inbox_user_popup_seen "
        "ON inbox_messages (user_id, popup_id, seen_popup_at) "
        "WHERE popup_id IS NOT NULL"
    )
    # 팝업당 사용자 1행 — UPSERT 멱등성 보장
    op.execute(
        "CREATE UNIQUE INDEX uniq_inbox_user_popup "
        "ON inbox_messages (user_id, popup_id) "
        "WHERE popup_id IS NOT NULL"
    )

    # ── customer_inquiries ─────────────────────────────────────────────────
    op.create_table(
        "customer_inquiries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="inquiry_status_enum", create_type=False),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_inquiries_status_created",
        "customer_inquiries",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_inquiries_user_created",
        "customer_inquiries",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_inquiries_user_created", table_name="customer_inquiries")
    op.drop_index("idx_inquiries_status_created", table_name="customer_inquiries")
    op.drop_table("customer_inquiries")

    op.execute("DROP INDEX IF EXISTS uniq_inbox_user_popup")
    op.execute("DROP INDEX IF EXISTS idx_inbox_user_popup_seen")
    op.execute("DROP INDEX IF EXISTS idx_inbox_user_unread")
    op.drop_table("inbox_messages")

    op.drop_index("idx_popups_active_window", table_name="popups")
    op.drop_table("popups")

    op.execute("DROP INDEX IF EXISTS idx_notices_published_segment")
    op.drop_table("notices")

    op.execute("DROP TYPE IF EXISTS inquiry_status_enum")
    op.execute("DROP TYPE IF EXISTS inbox_message_type_enum")
    op.execute("DROP TYPE IF EXISTS segment_target_enum")

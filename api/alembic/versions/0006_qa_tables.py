"""qa_logs · qa_feedback 테이블 생성 — Story 2.1 Q&A 데이터 모델.

qa_logs: 질의응답 기록. user_id FK ON DELETE SET NULL (탈퇴 시 익명화 — NFR-C4).
qa_feedback: 질의당 좋아요/나쁨 피드백. qa_log_id UNIQUE (1:1 관계).

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("rule_matched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_qa_logs_user_id",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "idx_qa_logs_user_id_created_at",
        "qa_logs",
        ["user_id", "created_at"],
    )

    op.create_table(
        "qa_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("qa_log_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.String(4), nullable=False),
        sa.Column("change_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["qa_log_id"],
            ["qa_logs.id"],
            name="fk_qa_feedback_qa_log_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("rating IN ('good', 'bad')", name="ck_qa_feedback_rating"),
    )

    op.create_index(
        "uq_qa_feedback_qa_log_id",
        "qa_feedback",
        ["qa_log_id"],
        unique=True,
    )

    op.create_index(
        "idx_qa_feedback_qa_log_id",
        "qa_feedback",
        ["qa_log_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_qa_feedback_qa_log_id", table_name="qa_feedback")
    op.drop_index("uq_qa_feedback_qa_log_id", table_name="qa_feedback")
    op.drop_table("qa_feedback")
    op.drop_index("idx_qa_logs_user_id_created_at", table_name="qa_logs")
    op.drop_table("qa_logs")

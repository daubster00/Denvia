"""#132 부관리자별 질의응답 검토 조회 설정 테이블.

전역 단일 설정과 별개로 부관리자(제한 등급) 각각에게 독립적인 조회기간+평가필터를
부여하기 위한 테이블. 행이 없는 부관리자는 전역 기본값 + 필터 'all' 로 동작(기존과 동일).
"""
import sqlalchemy as sa
from alembic import op

revision = "0071_qa_review_admin_settings"
down_revision = "0070_prompt_suppresses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_review_admin_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "admin_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("max_lookback_days", sa.Integer(), nullable=True),
        sa.Column(
            "rating_scope", sa.String(length=10), nullable=False, server_default="all"
        ),
        sa.Column(
            "updated_by_admin_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("admin_id", name="uq_qa_review_admin_settings_admin_id"),
    )


def downgrade() -> None:
    op.drop_table("qa_review_admin_settings")

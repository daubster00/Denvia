"""users 테이블 초기 생성 — CITEXT 확장 + partial UNIQUE index.

Revision ID: 0001
Revises:
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CITEXT 확장 활성화 (대소문자 무관 이메일 비교)
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("role", sa.String(10), nullable=False, server_default="user"),
        sa.Column(
            "subscription_status",
            sa.String(10),
            nullable=False,
            server_default="free",
        ),
        sa.Column("segment", sa.String(20), nullable=True),
        sa.Column("years_of_experience", sa.SmallInteger(), nullable=True),
        sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "must_reset_password", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("withdrawn_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
    )

    # 탈퇴 전 계정만 UNIQUE 적용 (재가입 허용)
    op.execute(
        "CREATE UNIQUE INDEX uq_users_email ON users(email) WHERE withdrawn_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_users_phone ON users(phone) WHERE withdrawn_at IS NULL"
    )


def downgrade() -> None:
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS citext")

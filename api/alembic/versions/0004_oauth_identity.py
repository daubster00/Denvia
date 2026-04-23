"""oauth_identity 테이블 생성 — Story 1.6 소셜 로그인 식별자 저장.

provider(kakao/google/naver) + provider_sub UNIQUE 조합으로 동일 소셜 계정을
단일 users 레코드에 매핑한다. user_id FK는 ON DELETE CASCADE (Story 1.7 탈퇴 호환).

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_identity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("provider_sub", sa.String(255), nullable=False),
        sa.Column(
            "linked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_oauth_identity_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "provider IN ('kakao', 'google', 'naver')",
            name="ck_oauth_identity_provider",
        ),
    )

    # 매칭 키 — (provider, provider_sub) UNIQUE
    op.create_index(
        "uq_oauth_identity_provider_sub",
        "oauth_identity",
        ["provider", "provider_sub"],
        unique=True,
    )

    # find-id signup_method 조회용 (Story 1.5 확장)
    op.create_index(
        "idx_oauth_identity_user_id",
        "oauth_identity",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_oauth_identity_user_id", table_name="oauth_identity")
    op.drop_index("uq_oauth_identity_provider_sub", table_name="oauth_identity")
    op.drop_table("oauth_identity")

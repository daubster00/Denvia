"""Story 6.2 fix — users 테이블에 pre_block_status 컬럼 추가.

차단 전 subscription_status를 보존해 만료/해제 시 정확히 복원한다.
이 컬럼이 없으면 Pro 사용자를 차단 후 만료시키면 free로 강등되는 버그가 발생한다.

- pre_block_status: 차단 직전 subscription_status 값 ('free'|'pro'|…), NULL=차단 전 값 불명(안전 기본값: free)

down_revision='0023_popups_soft_delete'.
"""

from alembic import op
import sqlalchemy as sa

revision = "0024_pre_block_status"
down_revision = "0023_popups_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pre_block_status", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pre_block_status")

"""users 테이블 quota/delay override 컬럼 추가 — Story 2.3.

daily_quota_override: NULL = 전역 설정 사용, 0 = 즉시 차단, 양수 = 개별 한도 (AC-2, Epic 6 Story 6.2)
free_delay_override:  NULL = 전역 설정 사용, 0 = 지연 OFF, 양수 = 개별 지연 초 (AC-3, Epic 6 Story 6.3)
편집 UI/관리자 API는 Epic 6에서 구현 — 본 스토리는 컬럼 선행 추가만.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("daily_quota_override", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("free_delay_override", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "free_delay_override")
    op.drop_column("users", "daily_quota_override")

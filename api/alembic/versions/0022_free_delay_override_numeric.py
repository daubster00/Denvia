"""Story 6.3 — users.free_delay_override INT → NUMERIC(4,1) 타입 변경.

본 마이그레이션은 epics.md 6.3 AC-1의 "0~30초, 0.1초 단위" 정밀도 요구를
충족하기 위해 컬럼을 NUMERIC(4,1)으로 변경한다.

- INT → NUMERIC(4,1) ALTER TYPE은 PostgreSQL implicit cast로 기존 데이터 보존
  (예: 3 → 3.0). NULL 행은 NULL 그대로.
- downgrade는 NUMERIC → INTEGER cast이므로 ROUND 처리 후 INTEGER로 변환.
- ACCESS EXCLUSIVE lock 동반(테이블 rewrite). 사용자 row 수 < 수만이면
  1초 미만 예상.
- SQLite 비호환은 무시(본 프로젝트 PostgreSQL 16 단일 DB).

down_revision='0021_user_block_columns'.
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_free_delay_override_numeric"
down_revision = "0021_user_block_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "free_delay_override",
        type_=sa.Numeric(4, 1),
        existing_type=sa.Integer(),
        existing_nullable=True,
        postgresql_using="free_delay_override::NUMERIC(4,1)",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "free_delay_override",
        type_=sa.Integer(),
        existing_type=sa.Numeric(4, 1),
        existing_nullable=True,
        postgresql_using="ROUND(free_delay_override)::INTEGER",
    )

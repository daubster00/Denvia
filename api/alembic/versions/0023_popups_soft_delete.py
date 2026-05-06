"""Story 7.2 — popups soft delete + updated_at + partial index 재생성.

deleted_at: 관리자 삭제 시점 기록(NULL = 살아있음).
updated_at: 마지막 수정 시각(생성·is_active 토글·편집 등 모든 UPDATE에서 갱신).
idx_popups_active_window: deleted_at IS NULL 조건 partial index로 재생성하여
soft delete된 팝업이 사용자 측 조회 인덱스 스캔에서 자동 제외되도록 한다.
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_popups_soft_delete"
down_revision = "0022_free_delay_override_numeric"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    op.execute("DROP INDEX IF EXISTS idx_popups_active_window")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_popups_active_window "
        "ON popups (is_active, display_start, display_end) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_popups_active_window")
    op.create_index(
        "idx_popups_active_window",
        "popups",
        ["is_active", "display_start", "display_end"],
    )
    op.drop_column("popups", "updated_at")
    op.drop_column("popups", "deleted_at")

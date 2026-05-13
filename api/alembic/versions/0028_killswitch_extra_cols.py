"""Story 9.2 — killswitch_states 컬럼 2종 추가.

- deactivated_by  : BIGINT NULL FK users.id ON DELETE SET NULL — 수동 해제 actor 추적
- year_month      : CHAR(7) NULL — auto_free_only 활성 시점의 예산 기준월(manual_total은 NULL)

기존 0012 마이그레이션의 killswitch_states 테이블·partial UNIQUE·partial 인덱스는 유지
(재생성 불필요). ALTER TABLE만 수행. 기존 row는 두 신규 컬럼이 NULL로 남는다.

down_revision='0027_popups_redesign'.
"""

from alembic import op

revision = "0028_killswitch_extra_cols"
down_revision = "0027_popups_redesign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) deactivated_by — 수동 해제 actor (FK users.id ON DELETE SET NULL).
    op.execute(
        "ALTER TABLE killswitch_states "
        "ADD COLUMN IF NOT EXISTS deactivated_by BIGINT NULL"
    )
    op.execute(
        "ALTER TABLE killswitch_states "
        "DROP CONSTRAINT IF EXISTS fk_killswitch_states_deactivated_by"
    )
    op.execute(
        "ALTER TABLE killswitch_states "
        "ADD CONSTRAINT fk_killswitch_states_deactivated_by "
        "FOREIGN KEY (deactivated_by) REFERENCES users(id) ON DELETE SET NULL"
    )

    # 2) year_month — auto_free_only 활성 row의 기준월 (manual_total은 NULL 유지).
    op.execute(
        "ALTER TABLE killswitch_states "
        "ADD COLUMN IF NOT EXISTS year_month CHAR(7) NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE killswitch_states "
        "DROP CONSTRAINT IF EXISTS fk_killswitch_states_deactivated_by"
    )
    op.execute("ALTER TABLE killswitch_states DROP COLUMN IF EXISTS year_month")
    op.execute("ALTER TABLE killswitch_states DROP COLUMN IF EXISTS deactivated_by")

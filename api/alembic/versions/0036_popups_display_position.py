"""Story 7.2 v3 — 팝업 노출 위치 컬럼 추가.

추가 컬럼:
- display_position : 'center'/'top'/'bottom'/'bottom_left'/'bottom_right'
  PC 화면에서 팝업 모달이 뜰 위치. 모바일은 화면이 좁아 항상 가운데 고정이라
  컬럼은 저장하되 클라이언트에서 무시한다.

down_revision='0035_payment_events_refund_kind'.
"""

from alembic import op

revision = "0036_popups_display_position"
down_revision = "0035_payment_events_refund_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Enum 타입 신규 생성 (멱등)
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'popup_display_position_enum') THEN "
        "CREATE TYPE popup_display_position_enum AS ENUM "
        "('center', 'top', 'bottom', 'bottom_left', 'bottom_right'); "
        "END IF; END $$;"
    )

    # 2) 컬럼 추가 — 기존 행은 'center' 기본값으로 채워짐
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS display_position popup_display_position_enum "
        "NOT NULL DEFAULT 'center'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE popups DROP COLUMN IF EXISTS display_position")
    op.execute("DROP TYPE IF EXISTS popup_display_position_enum")

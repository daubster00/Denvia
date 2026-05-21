"""Story 7.2 v4 — 팝업 노출 위치 옵션 재구성.

기존 5종(center/top/bottom/bottom_left/bottom_right) → 4종(center/left/right/custom)으로
교체하고, custom 모드용 직접 좌표 컬럼 두 개를 추가한다.

값 매핑:
- top, bottom         → center  (세로 기준 단순 가운데로 합침)
- bottom_left         → left
- bottom_right        → right
- center              → center (그대로)

신규 컬럼:
- display_position_top_px  : 위에서 N px (custom 일 때만 의미)
- display_position_left_px : 왼쪽에서 N px (custom 일 때만 의미)

PostgreSQL 은 enum 값 제거를 직접 지원하지 않으므로 타입을 한 번 rename → 신규 생성 →
USING 캐스팅으로 컬럼 변환 → 구 타입 drop 패턴으로 처리한다.

down_revision='0041_board_status_completed'.
"""

from __future__ import annotations

from alembic import op


revision = "0042_popup_position_redesign"
down_revision = "0041_board_status_completed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DEFAULT 분리 — 타입 교체 시 충돌 방지
    op.execute("ALTER TABLE popups ALTER COLUMN display_position DROP DEFAULT")

    # 1) 구 enum 백업
    op.execute(
        "ALTER TYPE popup_display_position_enum "
        "RENAME TO popup_display_position_enum_old"
    )

    # 2) 신규 enum 생성
    op.execute(
        "CREATE TYPE popup_display_position_enum AS ENUM "
        "('center', 'left', 'right', 'custom')"
    )

    # 3) 컬럼 타입 교체 + 기존 값 매핑
    op.execute(
        "ALTER TABLE popups "
        "ALTER COLUMN display_position TYPE popup_display_position_enum "
        "USING (CASE display_position::text "
        "WHEN 'top' THEN 'center' "
        "WHEN 'bottom' THEN 'center' "
        "WHEN 'bottom_left' THEN 'left' "
        "WHEN 'bottom_right' THEN 'right' "
        "ELSE 'center' END)::popup_display_position_enum"
    )

    # 4) DEFAULT 복원
    op.execute(
        "ALTER TABLE popups ALTER COLUMN display_position SET DEFAULT 'center'"
    )

    # 5) 구 enum 제거
    op.execute("DROP TYPE popup_display_position_enum_old")

    # 6) 직접 좌표 컬럼 추가 (custom 모드 전용)
    op.execute(
        "ALTER TABLE popups ADD COLUMN IF NOT EXISTS "
        "display_position_top_px INTEGER NULL"
    )
    op.execute(
        "ALTER TABLE popups ADD COLUMN IF NOT EXISTS "
        "display_position_left_px INTEGER NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE popups DROP COLUMN IF EXISTS display_position_left_px"
    )
    op.execute(
        "ALTER TABLE popups DROP COLUMN IF EXISTS display_position_top_px"
    )

    op.execute("ALTER TABLE popups ALTER COLUMN display_position DROP DEFAULT")
    op.execute(
        "ALTER TYPE popup_display_position_enum "
        "RENAME TO popup_display_position_enum_new"
    )
    op.execute(
        "CREATE TYPE popup_display_position_enum AS ENUM "
        "('center', 'top', 'bottom', 'bottom_left', 'bottom_right')"
    )
    op.execute(
        "ALTER TABLE popups "
        "ALTER COLUMN display_position TYPE popup_display_position_enum "
        "USING (CASE display_position::text "
        "WHEN 'left' THEN 'bottom_left' "
        "WHEN 'right' THEN 'bottom_right' "
        "WHEN 'custom' THEN 'center' "
        "ELSE 'center' END)::popup_display_position_enum"
    )
    op.execute(
        "ALTER TABLE popups ALTER COLUMN display_position SET DEFAULT 'center'"
    )
    op.execute("DROP TYPE popup_display_position_enum_new")

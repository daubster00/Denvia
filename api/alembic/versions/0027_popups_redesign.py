"""Story 7.2 v2 — 팝업 전면 재설계.

추가 컬럼:
- target_device  : 'pc'/'mobile'/'both' — 노출 디바이스
- popup_type     : 'image'/'editor' — 한 장 이미지 vs Tiptap 본문
- image_url      : 'image' 타입에서 사용 (TEXT NULL)
- sort_order     : 캐러셀 노출 순서 (작은 값 먼저)

기타 변경:
- popups.body_html → NULL 허용 (image 타입은 본문 없음)
- ck_popups_type_payload CHECK 추가 — image면 image_url 필수, editor면 body_html 필수
- 레거시 정리: inbox_messages WHERE popup_id IS NOT NULL 일괄 삭제
  (v1에서 팝업 닫기로 자동 보관되던 행 — 사용자가 "쪽지함에 팝업이 뜬다"고 보고한 원인)

down_revision='0026_inquiry_replies'.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_popups_redesign"
down_revision = "0026_inquiry_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Enum 타입 신규 생성
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'popup_target_device_enum') THEN "
        "CREATE TYPE popup_target_device_enum AS ENUM ('pc', 'mobile', 'both'); "
        "END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'popup_type_enum') THEN "
        "CREATE TYPE popup_type_enum AS ENUM ('image', 'editor'); "
        "END IF; END $$;"
    )

    # 2) 컬럼 4종 추가 (멱등)
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS target_device popup_target_device_enum "
        "NOT NULL DEFAULT 'both'"
    )
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS popup_type popup_type_enum "
        "NOT NULL DEFAULT 'editor'"
    )
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS image_url TEXT NULL"
    )
    op.execute(
        "ALTER TABLE popups "
        "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
    )

    # 3) body_html NULL 허용 (image 타입을 위해)
    op.execute("ALTER TABLE popups ALTER COLUMN body_html DROP NOT NULL")

    # 4) 타입별 payload CHECK
    op.execute(
        "ALTER TABLE popups DROP CONSTRAINT IF EXISTS ck_popups_type_payload"
    )
    op.execute(
        "ALTER TABLE popups ADD CONSTRAINT ck_popups_type_payload CHECK ("
        "(popup_type = 'image' AND image_url IS NOT NULL) "
        "OR (popup_type = 'editor' AND body_html IS NOT NULL)"
        ")"
    )

    # 5) 캐러셀 정렬용 인덱스 — 활성·기간 내 팝업의 sort_order 기준 스캔 가속
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_popups_active_carousel "
        "ON popups (target_device, sort_order, display_start) "
        "WHERE deleted_at IS NULL AND is_active = TRUE"
    )

    # 6) 레거시 정리 — v1 "팝업 닫기 → inbox 보관" 행 일괄 삭제
    #    사용자 피드백("팝업이 쪽지함에 들어간다") 직접 해소.
    #    공지(notice_id) 행은 보존, popup_id 행만 삭제.
    op.execute("DELETE FROM inbox_messages WHERE popup_id IS NOT NULL")


def downgrade() -> None:
    # 레거시 inbox 행은 복구 불가능 — downgrade에서 데이터 복원 안 함.
    op.execute("DROP INDEX IF EXISTS idx_popups_active_carousel")
    op.execute(
        "ALTER TABLE popups DROP CONSTRAINT IF EXISTS ck_popups_type_payload"
    )
    # body_html NULL → 빈 문자열로 채워 NOT NULL 복원
    op.execute("UPDATE popups SET body_html = '' WHERE body_html IS NULL")
    op.execute("ALTER TABLE popups ALTER COLUMN body_html SET NOT NULL")
    op.execute("ALTER TABLE popups DROP COLUMN IF EXISTS sort_order")
    op.execute("ALTER TABLE popups DROP COLUMN IF EXISTS image_url")
    op.execute("ALTER TABLE popups DROP COLUMN IF EXISTS popup_type")
    op.execute("ALTER TABLE popups DROP COLUMN IF EXISTS target_device")
    op.execute("DROP TYPE IF EXISTS popup_type_enum")
    op.execute("DROP TYPE IF EXISTS popup_target_device_enum")

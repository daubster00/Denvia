"""관리자 수정요청 게시판 — board_post_status_enum 에 'completed' 값 추가.

0040 에서 정의한 상태 4종(review/in_progress/rejected/on_hold)에
"수정완료(completed)"를 추가한다. 운영 중 btmdesign 마스터 계정이
수정 작업을 마치면 review/in_progress → completed 로 전환할 수 있도록 한다.

PostgreSQL 12+ 에서는 `ALTER TYPE ... ADD VALUE IF NOT EXISTS` 가
트랜잭션 내부에서 동작한다(같은 트랜잭션에서 신규 값을 즉시 사용하지 않는 한).
본 마이그레이션은 enum 확장만 수행하므로 안전하다.

down_revision='0040_admin_board'.
"""

from __future__ import annotations

from alembic import op

revision = "0041_board_status_completed"
down_revision = "0040_admin_board"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE board_post_status_enum ADD VALUE IF NOT EXISTS 'completed'"
    )


def downgrade() -> None:
    # PostgreSQL 은 ENUM 값 제거를 직접 지원하지 않는다(타입 재생성 필요).
    # 운영 데이터 손실 위험이 크므로 downgrade 는 no-op 으로 둔다.
    pass

"""관리자 수정요청 게시판 — board_post_status_enum 에 'rework'(추가수정) 값 추가.

수정완료(completed) 처리된 글에 대해 운영자가 다시 추가 수정을 요청할 수 있도록
"추가수정(rework)" 상태를 추가한다. 목록/드롭다운에서는 요청사항검토(review)
바로 다음 순서에 배치된다(정렬 우선순위는 admin_board_service.STATUS_SORT_ORDER).

0041 과 동일하게 enum 확장만 수행하므로 트랜잭션 내부에서 안전하다.

down_revision='0066_email_unique_per_role'.
"""

from __future__ import annotations

from alembic import op

revision = "0067_board_status_rework"
down_revision = "0066_email_unique_per_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE board_post_status_enum ADD VALUE IF NOT EXISTS 'rework'"
    )


def downgrade() -> None:
    # PostgreSQL 은 ENUM 값 제거를 직접 지원하지 않는다(타입 재생성 필요).
    # 운영 데이터 손실 위험이 크므로 downgrade 는 no-op 으로 둔다.
    pass

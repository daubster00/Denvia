"""Story 9.1 — 관리자 결제 기록 타임라인용 인덱스 추가.

본 마이그레이션은 GET /api/v1/admin/payments/events의 from/to 범위 + 정렬,
user_id 필터 + 결제 시점 정렬이 p95 ≤ 1.5초(Story 9.1 AC-7)를 충족하도록 다음을 추가한다:

1. idx_payment_events_created_at  : payment_events.created_at DESC (타임라인 범위 + 정렬)
2. idx_payments_user_id_charged_at: payments(user_id, charged_at DESC NULLS LAST)

CONCURRENTLY 미적용 사유: env.py가 트랜잭션 안에서 마이그레이션을 실행하므로
autocommit_block 우회가 가능하나 dev/CI에서 idle-in-transaction 세션과 충돌해
무한 대기로 빠지는 케이스를 확인했다. 본 코드베이스의 다른 인덱스 마이그레이션
(0020 admin_users_search)도 평문 CREATE INDEX를 사용한다. 운영 환경에서는
DBA가 CONCURRENTLY로 별도 적용해도 무방하며, 본 마이그레이션은 IF NOT EXISTS
가드로 멱등하므로 수동 선행 적용 후에도 충돌하지 않는다.

down_revision='0024_pre_block_status'.
"""

from alembic import op

revision = "0025_payment_events_admin_idx"
down_revision = "0024_pre_block_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_payment_events_created_at "
        "ON payment_events (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_payments_user_id_charged_at "
        "ON payments (user_id, charged_at DESC NULLS LAST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_payments_user_id_charged_at")
    op.execute("DROP INDEX IF EXISTS idx_payment_events_created_at")

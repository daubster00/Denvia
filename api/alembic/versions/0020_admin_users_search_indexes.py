"""Story 6.1 — Admin 사용자 통합 검색용 인덱스 추가.

본 마이그레이션은 GET /api/v1/admin/users 의 ILIKE 통합 검색이 PostgreSQL의
GIN trigram 인덱스를 사용해 p95 ≤ 1초(NFR-P5)를 충족하도록 다음을 추가한다:

1. pg_trgm 확장 (CREATE EXTENSION IF NOT EXISTS — 이미 있으면 무해)
2. idx_users_email_trgm  : users.email 전체 GIN trigram (email 은 NOT NULL)
3. idx_users_phone_trgm  : users.phone partial GIN trigram (phone IS NOT NULL일 때만)
4. idx_billing_keys_card_last4 : billing_keys.card_last4 partial BTREE (is_active 만)

NOTE 0020 번호 사유: 작성 시점에 main 기준 0019까지만 적용된 상태였고,
Story 7.2가 별도 분기에서 0020(popups deleted_at)을 만들었으나 main 머지 전이라
본 스토리 마이그레이션은 0020 으로 적용. 7.2 머지 후 충돌 시 measurement-side
에서 번호 재배치 또는 분기 head 통합 처리.

down_revision='0019_payment_period_snapshot'.

downgrade는 인덱스만 DROP — pg_trgm 확장은 다른 의존성이 있을 수 있어
정책상 보존(downgrade 트레이드오프 표준).
"""

from alembic import op

revision = "0020_admin_users_search_indexes"
down_revision = "0019_payment_period_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. pg_trgm 확장 — 이미 있으면 무해
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. users.email GIN trigram — email은 NOT NULL이므로 partial 불필요
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_email_trgm "
        "ON users USING GIN (email gin_trgm_ops)"
    )

    # 3. users.phone GIN trigram — NULL 가능 컬럼이므로 partial 적용
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_phone_trgm "
        "ON users USING GIN (phone gin_trgm_ops) "
        "WHERE phone IS NOT NULL"
    )

    # 4. billing_keys.card_last4 partial BTREE — 활성 빌링키만 매칭
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_billing_keys_card_last4 "
        "ON billing_keys (card_last4) "
        "WHERE is_active = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_billing_keys_card_last4")
    op.execute("DROP INDEX IF EXISTS idx_users_phone_trgm")
    op.execute("DROP INDEX IF EXISTS idx_users_email_trgm")
    # pg_trgm 확장은 의도적으로 보존 — 다른 스토리가 의존할 수 있음

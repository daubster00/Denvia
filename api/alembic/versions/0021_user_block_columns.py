"""Story 6.2 — users 테이블에 차단/Pro/last_login 4 컬럼 추가.

본 마이그레이션은 다음을 추가한다:

1. users.blocked_until        : 수동 차단 만료 시각 (NULL=영구 또는 미차단)
2. users.block_reason          : 차단 사유 메모 (관리자 운영 메모, 사용자 측 비공개)
3. users.pro_granted_by_admin  : 결제 없이 관리자 부여 Pro 플래그 (default=false)
4. users.last_login_at         : 최근 로그인 시각 (auth_service.login 1줄 update로 채움)
5. idx_users_blocked_until     : partial GIN 대신 BTREE — blocked_until IS NOT NULL 일 때만
                                 (anomaly_tasks.expire_blocks 매시간 정각 0분 스캔 비용 최소화)

down_revision='0020_admin_users_search_indexes'.

downgrade는 4 컬럼 + 1 인덱스를 명시적으로 DROP한다.
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_user_block_columns"
down_revision = "0020_admin_users_search_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 4 컬럼 추가 — pro_granted_by_admin 만 NOT NULL DEFAULT FALSE, 나머지 NULLABLE
    op.add_column(
        "users",
        sa.Column("blocked_until", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("block_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "pro_granted_by_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # partial BTREE index — expire_blocks 스캔 시 NULL 행 제외
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_blocked_until "
        "ON users (blocked_until) "
        "WHERE blocked_until IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_blocked_until")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "pro_granted_by_admin")
    op.drop_column("users", "block_reason")
    op.drop_column("users", "blocked_until")

"""users.anomaly_throttled_at 컬럼 + anomaly_event_type enum 확장.

신규 이상탐지 규칙(편차 +1, '답변 완료 시각 기준 3초 이내 연속 3회'):
  - users.anomaly_throttled_at  : 자동 throttle 적용 시각 (NULL=throttle 미적용)
                                  관리자가 수동 해제할 때까지 지속.
  - anomaly_event_type ENUM     : 'rapid_followup_questions' 값 추가.
  - idx_users_anomaly_throttled_at : partial BTREE (NULL 행 제외) — 관리자 목록 필터용.

down_revision='0043_phone_unique_per_role'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_anomaly_throttle"
down_revision = "0043_phone_unique_per_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) users.anomaly_throttled_at TIMESTAMPTZ NULL
    op.add_column(
        "users",
        sa.Column("anomaly_throttled_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_anomaly_throttled_at "
        "ON users (anomaly_throttled_at) "
        "WHERE anomaly_throttled_at IS NOT NULL"
    )

    # 2) anomaly_event_type 에 'rapid_followup_questions' 추가 (idempotent).
    #    Postgres 는 ENUM 값을 트랜잭션 안에서 ALTER 후 즉시 사용할 수 없으므로
    #    COMMIT 필요. Alembic 의 기본 트랜잭션 모드를 풀어주는 autocommit_block 사용.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE anomaly_event_type ADD VALUE IF NOT EXISTS 'rapid_followup_questions'"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_anomaly_throttled_at")
    op.drop_column("users", "anomaly_throttled_at")
    # ENUM 값 제거는 Postgres 에서 비파괴적 다운그레이드가 불가능 — 빈 값으로 남겨둔다.
    # 필요 시 DBA 가 새 타입으로 교체하는 식의 별도 마이그레이션을 작성한다.

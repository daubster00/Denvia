"""Story 4.6 — notification_queue (template_code, created_at DESC) 복합 인덱스 추가.

배경:
- 관리자 알림톡 관리 페이지 `/admin/alimtalk` 의 통계 집계 쿼리(`GROUP BY template_code, status`)
  + 템플릿별 발송 로그 cursor pagination 모두 본 인덱스를 사용한다.
- 운영 row 수가 누적되면 단일 컬럼 인덱스만으로는 느림.

설계 결정 — 평문 CREATE INDEX 채택:
- Alembic + async psycopg 환경에서 `CREATE INDEX CONCURRENTLY` 는 트랜잭션 분리가 동작하지 않음
  (psycopg.errors.ActiveSqlTransaction). Story 9.1 / 0020 패턴 답습.
- 운영 적용 시 짧은 락이 걸리지만 notification_queue 는 INSERT 빈도가 낮아 영향 미미.
- 운영 무중단 적용이 필요하면 alembic 외부에서 수동 `CREATE INDEX CONCURRENTLY` 선행 적용 후
  본 마이그가 `IF NOT EXISTS` 가드로 통과한다.

down_revision='0059_login_locked_until'.
"""

from __future__ import annotations

from alembic import op


revision = "0060_alimtalk_idx"
down_revision = "0059_login_locked_until"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_queue_template_created "
        "ON notification_queue (template_code, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notification_queue_template_created")

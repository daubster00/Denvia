"""Story 10.3 종결 — 활성 admin의 admin_grade NOT NULL 강제 (partial CHECK).

배경:
- 0054(`admin_rbac_foundation`)에서 admin_grade 컬럼을 추가하고 활성 관리자에 한해
  master/operator 백필을 마쳤다. 이후 모든 관리자 가입 경로는 grade를 명시적으로 설정한다.
- 인계 확인 결과 `withdrawn_at IS NULL` 활성 admin 중 admin_grade NULL은 0명. 탈퇴자 2명만 NULL.
- 운영 모든 가드 코드가 `withdrawn_at IS NULL` 가드와 함께 동작하므로 partial constraint가 적합.

설계 결정:
- 탈퇴자(withdrawn_at IS NOT NULL)는 NULL 허용. 가입 당시 NULL이었던 과거 데이터를 추측 backfill하지 않는다.
- role='admin' AND withdrawn_at IS NULL 일 때만 admin_grade NOT NULL 강제.
- CHECK constraint로 표현 — partial index가 아니라 row-level invariant.

down_revision='0060_alimtalk_idx'.
"""

from __future__ import annotations

from alembic import op


revision = "0061_admin_grade_active_notnull"
down_revision = "0060_alimtalk_idx"
branch_labels = None
depends_on = None


_CONSTRAINT_NAME = "ck_users_active_admin_grade_required"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT {_CONSTRAINT_NAME} "
        "CHECK (NOT (role = 'admin' AND withdrawn_at IS NULL AND admin_grade IS NULL))"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}")

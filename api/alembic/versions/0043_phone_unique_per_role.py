"""users.phone 유니크 제약을 role 단위 partial unique 로 분리.

기존: uq_users_phone — 전체 활성 사용자(WHERE withdrawn_at IS NULL) 글로벌 유니크.
변경: role 별로 두 개의 partial unique 인덱스로 분리.
  - uq_users_phone_admin     : role='admin'  AND phone IS NOT NULL AND withdrawn_at IS NULL
  - uq_users_phone_nonadmin  : role<>'admin' AND phone IS NOT NULL AND withdrawn_at IS NULL

효과: 관리자와 일반 회원이 같은 휴대폰 번호를 갖는 것을 허용한다
(관리자 본인 계정 수정 시 일반 회원과의 번호 중복으로 IntegrityError 가 나지 않음).
관리자끼리, 일반 회원끼리의 중복은 여전히 차단된다.

이메일(uq_users_email)은 로그인 식별자라 글로벌 유니크 유지.

down_revision='0042_popup_position_redesign'.
"""

from __future__ import annotations

from alembic import op


revision = "0043_phone_unique_per_role"
down_revision = "0042_popup_position_redesign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_phone")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_admin "
        "ON users (phone) "
        "WHERE role = 'admin' AND phone IS NOT NULL AND withdrawn_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_nonadmin "
        "ON users (phone) "
        "WHERE role <> 'admin' AND phone IS NOT NULL AND withdrawn_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_phone_admin")
    op.execute("DROP INDEX IF EXISTS uq_users_phone_nonadmin")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone "
        "ON users (phone) "
        "WHERE withdrawn_at IS NULL"
    )

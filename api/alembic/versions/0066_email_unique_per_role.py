"""users.email 유니크 제약을 role 단위 partial unique 로 분리.

기존: uq_users_email — 전체 활성 사용자(WHERE withdrawn_at IS NULL) 글로벌 유니크.
변경: role 별로 두 개의 partial unique 인덱스로 분리(0043 의 phone 분리와 동일한 방식).
  - uq_users_email_admin     : role='admin'  AND withdrawn_at IS NULL
  - uq_users_email_nonadmin  : role<>'admin' AND withdrawn_at IS NULL

배경: 2026-05-28 user/admin 멤버 완전 분리 설계가 확정되면서 가입/중복검사 로직은
같은 이메일이 일반 회원(role='user')과 관리자(role='admin')에 동시에 존재해도 허용하도록
바뀌었으나(signup_admin_pending 은 관리자 진영 내 중복만 검사), DB 이메일 유니크 인덱스는
글로벌인 채로 남아 있어 코드-DB 불일치가 있었다. 그 결과 이미 일반 회원으로 존재하는
이메일로 관리자 가입을 시도하면 앱 검사는 통과하지만 uq_users_email 위반으로 500 이 났다.
휴대폰(0043)과 동일하게 진영별로 분리해 설계와 DB 를 일치시킨다.

데이터 안전성: 인덱스만 교체하며 users 행 데이터는 전혀 건드리지 않는다.
기존 관리자끼리·일반 회원끼리는 여전히 이메일 중복이 차단되므로(기존 글로벌 유니크의
부분집합) 신규 partial 인덱스 생성이 실패할 여지가 없다.

down_revision='0065_qa_review'.
"""

from __future__ import annotations

from alembic import op


revision = "0066_email_unique_per_role"
down_revision = "0065_qa_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_email")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_admin "
        "ON users (email) "
        "WHERE role = 'admin' AND withdrawn_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_nonadmin "
        "ON users (email) "
        "WHERE role <> 'admin' AND withdrawn_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_email_admin")
    op.execute("DROP INDEX IF EXISTS uq_users_email_nonadmin")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
        "ON users (email) "
        "WHERE withdrawn_at IS NULL"
    )

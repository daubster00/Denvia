"""Epic 10 Story 10.1 — 다중 관리자 + 4등급 RBAC 기반 마이그레이션.

ADR-0001 편차 #6: 단일 관리자 운영의 한계(휴가·이양·업무 분담 불능)를 해소하기 위해
다중 관리자 + 4등급 권한 체계로 확장한다.

변경 사항:
1) ENUM 타입 `admin_grade_enum` 신규 생성 (master/operator/sub_operator/pending)
2) users 테이블에 4개 컬럼 추가 (모두 NULL 허용 — role!='admin'은 NULL)
   - admin_grade            admin_grade_enum NULL
   - admin_blocked_until    TIMESTAMPTZ NULL  (차단 만료, NULL=차단 없음)
   - admin_block_reason     TEXT NULL         (차단 사유)
   - admin_signup_at        TIMESTAMPTZ NULL  (pending 가입 신청 시각)
3) 신규 테이블 `admin_page_permissions` 생성
   - sub_operator 등급에 한해 페이지별 접근 권한을 개별 부여 (FR61)
   - UNIQUE(admin_user_id, page_route)
4) 마스터 단일성 partial UNIQUE 인덱스
   - uq_admin_grade_master ON users(admin_grade)
     WHERE admin_grade='master' AND withdrawn_at IS NULL
   - DB 레벨에서 master 등급 2개 동시 활성 불가 보장 (FR63)
5) 기존 관리자 백필
   - btmdesign@naver.com → master (단일)
   - 나머지 admin → operator

down_revision='0053_anomaly_sms_abuse'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0054_admin_rbac_foundation"
down_revision = "0053_anomaly_sms_abuse"
branch_labels = None
depends_on = None


_ADMIN_GRADES = ("master", "operator", "sub_operator", "pending")


def upgrade() -> None:
    # 1) admin_grade_enum 타입 생성
    admin_grade_enum = postgresql.ENUM(
        *_ADMIN_GRADES,
        name="admin_grade_enum",
        create_type=True,
    )
    admin_grade_enum.create(op.get_bind(), checkfirst=True)

    # 2) users 4개 컬럼 추가
    op.add_column(
        "users",
        sa.Column(
            "admin_grade",
            postgresql.ENUM(name="admin_grade_enum", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("admin_blocked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("admin_block_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("admin_signup_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3) admin_page_permissions 테이블 생성
    op.create_table(
        "admin_page_permissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("page_route", sa.String(length=64), nullable=False),
        sa.Column(
            "allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("granted_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_admin_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "admin_user_id",
            "page_route",
            name="uq_admin_page_permissions_user_route",
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_page_permissions_user "
        "ON admin_page_permissions (admin_user_id)"
    )

    # 4) 마스터 단일성 partial UNIQUE 인덱스 (DB 레벨 강제)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_grade_master "
        "ON users (admin_grade) "
        "WHERE admin_grade = 'master' AND withdrawn_at IS NULL"
    )

    # 5) 기존 관리자 백필
    #    btmdesign@naver.com이 admin 시드로 존재하면 master, 그 외 admin은 operator.
    op.execute(
        "UPDATE users "
        "SET admin_grade = 'master' "
        "WHERE role = 'admin' "
        "  AND withdrawn_at IS NULL "
        "  AND LOWER(email) = 'btmdesign@naver.com'"
    )
    op.execute(
        "UPDATE users "
        "SET admin_grade = 'operator' "
        "WHERE role = 'admin' "
        "  AND withdrawn_at IS NULL "
        "  AND admin_grade IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_admin_grade_master")
    op.execute("DROP INDEX IF EXISTS idx_admin_page_permissions_user")
    op.drop_table("admin_page_permissions")
    op.drop_column("users", "admin_signup_at")
    op.drop_column("users", "admin_block_reason")
    op.drop_column("users", "admin_blocked_until")
    op.drop_column("users", "admin_grade")
    op.execute("DROP TYPE IF EXISTS admin_grade_enum")

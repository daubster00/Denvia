"""Epic 10 Story 10.5 — 등급별 페이지 접근 권한 테이블.

ADR-0001 편차 #6 후속. 0054 에서 만든 user-level `admin_page_permissions` 는
운영 요구사항 변경(등급 단위 일괄 관리)으로 폐기하고, 등급별 권한 매트릭스로 대체한다.

변경:
1) DROP TABLE admin_page_permissions  (user-level, 0054 에서 생성)
2) CREATE TABLE admin_grade_page_permissions
   - admin_grade  admin_grade_enum  (operator / sub_operator 만 의미)
   - page_route   VARCHAR(64)
   - allowed      BOOLEAN
   - UNIQUE(admin_grade, page_route)
   - CHECK admin_grade IN ('operator','sub_operator')
3) 초기 시드 — 9개 1차 라우트 × 2개 등급 = 18행
   operator    : 전부 allowed=true  (마스터 다음 권한, 기본 전체 접근)
   sub_operator: 전부 allowed=false (기본 차단, 마스터/운영자가 페이지별로 부여)

down_revision='0054_admin_rbac_foundation'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0055_admin_grade_page_perms"
down_revision = "0054_admin_rbac_foundation"
branch_labels = None
depends_on = None


# 권한 매트릭스가 다루는 1차 라우트 — api/src/constants/admin_pages.py 와 동일해야 함.
_DEFAULT_ROUTES = [
    "/admin",
    "/admin/users",
    "/admin/anomaly",
    "/admin/content",
    "/admin/rag",
    "/admin/finance",
    "/admin/cs",
    "/admin/board",
    "/admin/settings",
]


def upgrade() -> None:
    # 1) 기존 user-level 테이블 제거 (0054 에서 만들어진 것)
    op.execute("DROP INDEX IF EXISTS idx_admin_page_permissions_user")
    op.execute("DROP TABLE IF EXISTS admin_page_permissions")

    # 2) 등급별 권한 테이블 생성
    op.create_table(
        "admin_grade_page_permissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "admin_grade",
            postgresql.ENUM(name="admin_grade_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("page_route", sa.String(length=64), nullable=False),
        sa.Column(
            "allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("updated_by_admin_id", sa.BigInteger(), nullable=True),
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
            ["updated_by_admin_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "admin_grade",
            "page_route",
            name="uq_admin_grade_page_permissions",
        ),
        sa.CheckConstraint(
            "admin_grade IN ('operator','sub_operator')",
            name="ck_admin_grade_page_permissions_grade",
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_grade_page_permissions_grade "
        "ON admin_grade_page_permissions (admin_grade)"
    )

    # 3) 시드 — operator 전부 true, sub_operator 전부 false.
    bind = op.get_bind()
    for route in _DEFAULT_ROUTES:
        bind.execute(
            sa.text(
                "INSERT INTO admin_grade_page_permissions "
                "(admin_grade, page_route, allowed) "
                "VALUES (:g, :r, :a) "
                "ON CONFLICT (admin_grade, page_route) DO NOTHING"
            ),
            {"g": "operator", "r": route, "a": True},
        )
        bind.execute(
            sa.text(
                "INSERT INTO admin_grade_page_permissions "
                "(admin_grade, page_route, allowed) "
                "VALUES (:g, :r, :a) "
                "ON CONFLICT (admin_grade, page_route) DO NOTHING"
            ),
            {"g": "sub_operator", "r": route, "a": False},
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_admin_grade_page_permissions_grade")
    op.drop_table("admin_grade_page_permissions")
    # 0054 의 user-level 테이블 복원
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

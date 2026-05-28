"""Epic 10 후속 — 관리자 등급 동적화(커스텀 등급 추가/삭제 지원).

배경: 0054/0055 에서 admin_grade 를 PG ENUM 으로 고정(master/operator/sub_operator/pending).
운영 요구사항으로 "추가 등급"을 도입해야 하므로 ENUM 을 VARCHAR(32) + admin_grades 메타
테이블 조합으로 전환한다.

변경:
1) admin_grades 테이블 신규 생성 (code PK, label UNIQUE, is_builtin, created_by_admin_id)
2) 내장 4종 시드: master / operator / sub_operator / pending (모두 is_builtin=true)
3) users.admin_grade : admin_grade_enum → VARCHAR(32)
4) admin_grade_page_permissions.admin_grade : admin_grade_enum → VARCHAR(32) + CHECK 제거
5) admin_grade_enum 타입 DROP
6) FK 추가
   - users.admin_grade → admin_grades.code  (ON UPDATE CASCADE, ON DELETE RESTRICT)
   - admin_grade_page_permissions.admin_grade → admin_grades.code (ON UPDATE CASCADE, ON DELETE CASCADE)
7) master 단일성 partial UNIQUE 인덱스는 컬럼 타입 변경 후에도 동일 의미로 유지(WHERE admin_grade='master').

down_revision='0056_user_watch_flags'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0057_admin_grades_dynamic"
down_revision = "0056_user_watch_flags"
branch_labels = None
depends_on = None


# is_builtin=true : 운영자가 본 등급 관리 페이지에서 수정·삭제 불가.
# - master   : RBAC 백본(개발자 단일). UI 에서는 숨김.
# - operator : 운영 주체. 항상 매트릭스 컬럼 + 등급 변경 옵션에 노출.
# - pending  : 신규 가입 신청 상태. 회귀용으로 유지.
# sub_operator (부운영자) 는 운영자가 자유롭게 추가·삭제할 수 있도록 is_builtin=false 로 시드.
_BUILTIN_GRADES: list[tuple[str, str, bool]] = [
    ("master", "마스터", True),
    ("operator", "운영 관리자", True),
    ("sub_operator", "부운영자", False),
    ("pending", "승인 대기", True),
]


def upgrade() -> None:
    bind = op.get_bind()

    # 1) admin_grades 테이블
    op.create_table(
        "admin_grades",
        sa.Column("code", sa.String(length=32), primary_key=True),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=True),
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
        sa.UniqueConstraint("label", name="uq_admin_grades_label"),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"], ["users.id"], ondelete="SET NULL"
        ),
    )

    # 2) 시드 — 4종 (master/operator/pending 만 is_builtin=true)
    for code, label, is_builtin in _BUILTIN_GRADES:
        bind.execute(
            sa.text(
                "INSERT INTO admin_grades (code, label, is_builtin) "
                "VALUES (:c, :l, :b) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"c": code, "l": label, "b": is_builtin},
        )

    # 3) users.admin_grade : ENUM → VARCHAR
    #    partial UNIQUE 인덱스(uq_admin_grade_master)는 WHERE admin_grade='master' 술어를
    #    쓰는데, PG 가 ENUM→TEXT 캐스트 후에도 술어 의미를 유지해 주지 않는 경우가 있어 안전하게 재생성.
    op.execute("DROP INDEX IF EXISTS uq_admin_grade_master")
    op.execute(
        "ALTER TABLE users ALTER COLUMN admin_grade TYPE VARCHAR(32) "
        "USING admin_grade::text"
    )

    # 4) admin_grade_page_permissions.admin_grade : ENUM → VARCHAR + CHECK 제거
    op.execute(
        "ALTER TABLE admin_grade_page_permissions "
        "DROP CONSTRAINT IF EXISTS ck_admin_grade_page_permissions_grade"
    )
    op.execute(
        "ALTER TABLE admin_grade_page_permissions ALTER COLUMN admin_grade TYPE VARCHAR(32) "
        "USING admin_grade::text"
    )

    # 5) admin_grade_enum 타입 DROP (이제 어떤 컬럼도 참조 안 함)
    op.execute("DROP TYPE IF EXISTS admin_grade_enum")

    # 6) FK 추가
    op.create_foreign_key(
        "fk_users_admin_grade",
        "users",
        "admin_grades",
        ["admin_grade"],
        ["code"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_admin_grade_page_permissions_grade",
        "admin_grade_page_permissions",
        "admin_grades",
        ["admin_grade"],
        ["code"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    # 7) master 단일성 partial UNIQUE 인덱스 재생성
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_grade_master "
        "ON users (admin_grade) "
        "WHERE admin_grade = 'master' AND withdrawn_at IS NULL"
    )


def downgrade() -> None:
    # 역방향: VARCHAR → ENUM 복원. 커스텀 등급이 이미 존재하면 실패할 수 있다(의도된 동작).
    bind = op.get_bind()

    # 커스텀 등급이 있으면 다운그레이드 거부 (ENUM 에 없는 값이 컬럼에 박혀 있을 수 있음)
    custom = bind.execute(
        sa.text("SELECT COUNT(*) FROM admin_grades WHERE is_builtin = false")
    ).scalar()
    if custom and int(custom) > 0:
        raise RuntimeError(
            "admin_grades 에 커스텀 등급이 존재합니다. 다운그레이드 전 모두 제거하세요."
        )

    # FK 제거
    op.drop_constraint(
        "fk_admin_grade_page_permissions_grade",
        "admin_grade_page_permissions",
        type_="foreignkey",
    )
    op.drop_constraint("fk_users_admin_grade", "users", type_="foreignkey")

    # partial UNIQUE 인덱스 임시 제거
    op.execute("DROP INDEX IF EXISTS uq_admin_grade_master")

    # ENUM 타입 재생성
    op.execute(
        "CREATE TYPE admin_grade_enum AS ENUM ('master','operator','sub_operator','pending')"
    )

    # VARCHAR → ENUM
    op.execute(
        "ALTER TABLE users ALTER COLUMN admin_grade TYPE admin_grade_enum "
        "USING admin_grade::admin_grade_enum"
    )
    op.execute(
        "ALTER TABLE admin_grade_page_permissions ALTER COLUMN admin_grade TYPE admin_grade_enum "
        "USING admin_grade::admin_grade_enum"
    )
    op.execute(
        "ALTER TABLE admin_grade_page_permissions "
        "ADD CONSTRAINT ck_admin_grade_page_permissions_grade "
        "CHECK (admin_grade IN ('operator','sub_operator'))"
    )

    # master partial UNIQUE 인덱스 재생성
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_grade_master "
        "ON users (admin_grade) "
        "WHERE admin_grade = 'master' AND withdrawn_at IS NULL"
    )

    # admin_grades 테이블 DROP
    op.drop_table("admin_grades")

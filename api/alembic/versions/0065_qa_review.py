"""#113 질의응답 검토 — qa_reviews + qa_review_settings 테이블.

운영진(sub_operator)이 사용자 질의응답을 검토해 굿/베드 + 코멘트를 남기고,
최고관리자(master/operator)가 검토완료 처리하는 신규 관리자 기능.
기존 qa_feedback(고객 피드백)과는 완전히 분리된 별도 개념·테이블이다.

1) qa_reviews         — qa_log 당 1행 검토 상태
2) qa_review_settings — 단일행 config (부관리자 조회 최대 과거 일수)
3) admin_grade_page_permissions 에 '/admin/qa-review' 페이지권한 기본값 시드
   - operator=true, sub_operator=true (부관리자용 기능이므로 기본 노출)
   - 커스텀 등급 = false (0058 방식과 동일)

down_revision='0064_board_feature_dev'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0065_qa_review"
down_revision = "0064_board_feature_dev"
branch_labels = None
depends_on = None


_PAGE_ROUTE = "/admin/qa-review"


def upgrade() -> None:
    # 1) qa_reviews
    op.create_table(
        "qa_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "qa_log_id",
            sa.BigInteger(),
            sa.ForeignKey("qa_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(length=4), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "rated_by_admin_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "change_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("qa_log_id", name="uq_qa_reviews_qa_log_id"),
        sa.CheckConstraint(
            "rating IS NULL OR rating IN ('good', 'bad')",
            name="ck_qa_reviews_rating",
        ),
    )
    # 목록은 최신순 정렬 + hidden 필터가 잦으므로 인덱스로 최적화.
    op.create_index(
        "ix_qa_reviews_qa_log_id",
        "qa_reviews",
        ["qa_log_id"],
    )
    op.execute(
        "CREATE INDEX ix_qa_reviews_visible_created_at "
        "ON qa_reviews (created_at) WHERE hidden_at IS NULL"
    )

    # 2) qa_review_settings (단일행)
    op.create_table(
        "qa_review_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column(
            "sub_operator_max_lookback_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("7"),
        ),
        sa.Column(
            "updated_by_admin_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_qa_review_settings_singleton"),
    )
    op.execute(
        "INSERT INTO qa_review_settings (id, sub_operator_max_lookback_days) "
        "VALUES (1, 7) ON CONFLICT (id) DO NOTHING"
    )

    # 3) 페이지권한 기본값 시드 — configurable 등급별.
    #    operator/sub_operator = true (부관리자용 기능이라 기본 노출), 커스텀 등급 = false.
    bind = op.get_bind()
    grade_rows = bind.execute(
        sa.text("SELECT code FROM admin_grades WHERE code NOT IN ('master', 'pending')")
    ).fetchall()
    for (code,) in grade_rows:
        allowed = code in ("operator", "sub_operator")
        bind.execute(
            sa.text(
                "INSERT INTO admin_grade_page_permissions "
                "(admin_grade, page_route, allowed) "
                "VALUES (:g, :r, :a) "
                "ON CONFLICT (admin_grade, page_route) DO NOTHING"
            ),
            {"g": code, "r": _PAGE_ROUTE, "a": allowed},
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM admin_grade_page_permissions WHERE page_route = :r"
        ).bindparams(r=_PAGE_ROUTE)
    )
    op.drop_table("qa_review_settings")
    op.execute("DROP INDEX IF EXISTS ix_qa_reviews_visible_created_at")
    op.drop_index("ix_qa_reviews_qa_log_id", table_name="qa_reviews")
    op.drop_table("qa_reviews")

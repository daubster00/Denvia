"""qa_feedback 검토완료 상태 추가 — 관리자가 피드백을 검토 후 '검토완료' 처리.

배경:
- 굿/베드 피드백 화면에서 BAD를 사용자 의도대로 수정한 뒤 관리자가 해당 행을
  '검토완료' 로 표시할 수 있어야 한다. 토글로 되돌리기도 가능.
- 원래 GOOD/BAD rating은 그대로 보존하고, 별도 컬럼으로 검토 상태를 표현한다.

설계:
- reviewed_at TIMESTAMPTZ NULL: NULL = 미검토, NOT NULL = 검토완료(타임스탬프 = 처리 시각).
- reviewed_by_user_id BIGINT NULL FK users(id) ON DELETE SET NULL:
  검토 처리한 관리자. 관리자가 탈퇴해도 검토완료 상태 자체는 유지.
- 부분 인덱스(reviewed_at IS NULL)로 '미검토만 빠르게 카운트' 쿼리 최적화.

down_revision = '0061_admin_grade_active_notnull'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0062_qa_feedback_reviewed"
down_revision = "0061_admin_grade_active_notnull"
branch_labels = None
depends_on = None


_FK_NAME = "fk_qa_feedback_reviewed_by_user_id_users"
_IDX_PENDING = "ix_qa_feedback_reviewed_at_null"
_IDX_REVIEWED = "ix_qa_feedback_reviewed_at"


def upgrade() -> None:
    op.add_column(
        "qa_feedback",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "qa_feedback",
        sa.Column("reviewed_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        _FK_NAME,
        "qa_feedback",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # 미검토(reviewed_at IS NULL) 카운트가 가장 자주 쓰이므로 부분 인덱스로 최적화.
    op.execute(
        f"CREATE INDEX {_IDX_PENDING} ON qa_feedback (created_at) "
        "WHERE reviewed_at IS NULL"
    )
    # 검토완료 시계열 집계용.
    op.create_index(
        _IDX_REVIEWED,
        "qa_feedback",
        ["reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_IDX_REVIEWED, table_name="qa_feedback")
    op.execute(f"DROP INDEX IF EXISTS {_IDX_PENDING}")
    op.drop_constraint(_FK_NAME, "qa_feedback", type_="foreignkey")
    op.drop_column("qa_feedback", "reviewed_by_user_id")
    op.drop_column("qa_feedback", "reviewed_at")

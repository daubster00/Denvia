"""user_watch_flags — 이상탐지 "주의 계정" 플래그 테이블.

이상탐지 리스트의 별 모양 버튼으로 관리자가 특정 계정을 주의 목록에 올릴 수 있다.
계정당 1행(user_id UNIQUE) — 같은 계정을 두 번 등록하지 못한다.

컬럼:
- user_id              사용자 PK(FK users.id ON DELETE CASCADE) — 탈퇴/삭제 시 같이 제거.
- flagged_by_admin_id  등록한 관리자(FK users.id ON DELETE SET NULL).
- source_anomaly_id    별을 처음 누른 이상 이벤트 PK(FK anomaly_events.id ON DELETE SET NULL).
- anomaly_type         별을 처음 누른 이상탐지 type 라벨 — anomaly가 지워져도 보존.
- created_at           등록 시각.

down_revision='0055_admin_grade_page_perms'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0056_user_watch_flags"
down_revision = "0055_admin_grade_page_perms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_watch_flags",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("flagged_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("source_anomaly_id", sa.BigInteger(), nullable=True),
        sa.Column("anomaly_type", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["flagged_by_admin_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_anomaly_id"],
            ["anomaly_events.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("user_id", name="uq_user_watch_flags_user"),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_watch_flags_created_at "
        "ON user_watch_flags (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_watch_flags_created_at")
    op.drop_table("user_watch_flags")

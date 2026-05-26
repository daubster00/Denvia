"""inbox_messages: type enum에 admin_dm 추가 + deleted_at(휴지통) 컬럼.

관리자 → 특정 사용자 1:1 안내 쪽지. notice_id/popup_id 모두 NULL이고
type='admin_dm'으로 식별한다. 발송자 추적용 created_by_admin_id도 함께 추가.

deleted_at: 사용자가 쪽지함에서 삭제 시 채워진다. 30일 후 영구 삭제 배치가
purge_old_inbox_messages 태스크에서 일괄 처리한다(retention_tasks.py).

CheckConstraint ck_inbox_source_type을 admin_dm 분기 포함하도록 갱신한다.

down_revision='0050_drop_question_block_cols'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0051_inbox_admin_dm"
down_revision = "0050_drop_question_block_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) ENUM에 admin_dm 추가 — PostgreSQL은 새 enum 값을 같은 트랜잭션 안에서
    #    참조할 수 없으므로 autocommit_block 으로 ALTER TYPE 단독 COMMIT 시킨다
    #    (0044/0046 동일 패턴).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE inbox_message_type_enum ADD VALUE IF NOT EXISTS 'admin_dm'"
        )

    # 2) 발송자 admin id + 휴지통 시각 컬럼
    op.add_column(
        "inbox_messages",
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "inbox_messages",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inbox_messages_created_by_admin",
        "inbox_messages",
        "users",
        ["created_by_admin_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3) CheckConstraint 재정의 — admin_dm 분기 추가
    op.execute("ALTER TABLE inbox_messages DROP CONSTRAINT IF EXISTS ck_inbox_source_type")
    op.create_check_constraint(
        "ck_inbox_source_type",
        "inbox_messages",
        "(notice_id IS NOT NULL AND popup_id IS NULL AND type IN ('notice','system','billing')) "
        "OR (popup_id IS NOT NULL AND notice_id IS NULL AND type = 'notice') "
        "OR (notice_id IS NULL AND popup_id IS NULL AND type IN ('system','billing','admin_dm'))",
    )

    # 4) 휴지통 purge 배치용 인덱스 (deleted_at IS NOT NULL인 행만)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inbox_deleted_at "
        "ON inbox_messages (deleted_at) "
        "WHERE deleted_at IS NOT NULL"
    )

    # 5) 기존 미읽음 인덱스는 deleted_at IS NULL 조건을 포함해 재생성한다 —
    #    휴지통에 들어간 쪽지는 미읽음 카운트/리스트에서 제외해야 한다.
    op.execute("DROP INDEX IF EXISTS idx_inbox_user_unread")
    op.execute(
        "CREATE INDEX idx_inbox_user_unread "
        "ON inbox_messages (user_id, is_read, created_at DESC) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # 인덱스 복원 (WHERE 절 없는 원본 형태)
    op.execute("DROP INDEX IF EXISTS idx_inbox_user_unread")
    op.execute(
        "CREATE INDEX idx_inbox_user_unread "
        "ON inbox_messages (user_id, is_read, created_at DESC)"
    )

    op.execute("DROP INDEX IF EXISTS idx_inbox_deleted_at")

    # CheckConstraint 원복
    op.execute("ALTER TABLE inbox_messages DROP CONSTRAINT IF EXISTS ck_inbox_source_type")
    op.create_check_constraint(
        "ck_inbox_source_type",
        "inbox_messages",
        "(notice_id IS NOT NULL AND popup_id IS NULL AND type IN ('notice','system','billing')) "
        "OR (popup_id IS NOT NULL AND notice_id IS NULL AND type = 'notice') "
        "OR (notice_id IS NULL AND popup_id IS NULL AND type IN ('system','billing'))",
    )

    # FK + 컬럼 제거
    op.drop_constraint(
        "fk_inbox_messages_created_by_admin",
        "inbox_messages",
        type_="foreignkey",
    )
    op.drop_column("inbox_messages", "deleted_at")
    op.drop_column("inbox_messages", "created_by_admin_id")

    # ENUM 값은 PostgreSQL에서 안전하게 제거할 방법이 없으므로 그대로 유지.
    # 사용된 적이 없다면 무해. 새 type을 만들어 swap하는 방법은 의존성 비용이 큼.

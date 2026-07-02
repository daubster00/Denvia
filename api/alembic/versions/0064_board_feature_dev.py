"""관리자 수정요청 게시판 — 추가개발 컨펌 플로우 + 파일 첨부.

1) board_post_status_enum 에 'confirm_requested'(컨펌요청) / 'confirmed'(컨펌) 추가.
   - 마스터가 추가개발비를 입력하면 status → confirm_requested
   - 운영자가 컨펌 버튼을 누르면 status → confirmed
2) admin_board_posts.dev_cost — 추가개발비(원). NULL = 미입력.
3) admin_board_attachments — 글 첨부파일(문서/압축/이미지). post 삭제 시 CASCADE.

PostgreSQL 12+ 에서 `ALTER TYPE ... ADD VALUE` 는 트랜잭션 안에서 동작한다.
본 마이그레이션은 신규 enum 값을 같은 트랜잭션에서 사용하지 않으므로 안전하다.

down_revision='0063_qa_log_prompt_text'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064_board_feature_dev"
down_revision = "0063_qa_log_prompt_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 상태 enum 확장 (신규 값은 같은 트랜잭션에서 사용하지 않음)
    op.execute(
        "ALTER TYPE board_post_status_enum ADD VALUE IF NOT EXISTS 'confirm_requested'"
    )
    op.execute(
        "ALTER TYPE board_post_status_enum ADD VALUE IF NOT EXISTS 'confirmed'"
    )

    # 2) 추가개발비 컬럼 (원 단위, NULL = 미입력)
    op.add_column(
        "admin_board_posts",
        sa.Column("dev_cost", sa.BigInteger(), nullable=True),
    )

    # 3) 첨부파일 테이블
    op.create_table(
        "admin_board_attachments",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "post_id",
            sa.BigInteger(),
            sa.ForeignKey("admin_board_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_admin_board_attachments_post_id",
        "admin_board_attachments",
        ["post_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_board_attachments_post_id",
        table_name="admin_board_attachments",
    )
    op.drop_table("admin_board_attachments")
    op.drop_column("admin_board_posts", "dev_cost")
    # PostgreSQL 은 ENUM 값 제거를 직접 지원하지 않는다(타입 재생성 필요).
    # 운영 데이터 손실 위험이 크므로 enum downgrade 는 no-op.

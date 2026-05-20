"""관리자 수정요청 게시판 — admin_board_posts + admin_board_comments.

관리자 콘솔 내부에서 수정사항을 등록·추적하는 사내용 게시판.
일반 사용자에게는 노출되지 않는다(관리자 라우터 + admin role 가드).

테이블:
1) admin_board_posts
   - id          BIGSERIAL PK
   - author_id   BIGINT FK users(id) ON DELETE RESTRICT  (작성자 관리자 계정)
   - category    VARCHAR(40) NOT NULL                    (프로젝트 영역 키; 앱 레벨 검증)
   - status      board_post_status_enum NOT NULL DEFAULT 'review'
                 review(요청사항검토) | in_progress(수정중) | rejected(수정불가) | on_hold(보류)
   - title       VARCHAR(200) NOT NULL
   - content_html TEXT NOT NULL                          (sanitize된 Tiptap 본문 HTML)
   - created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
   - updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
   - idx_admin_board_posts_status_created (status, created_at DESC)
   - idx_admin_board_posts_category_created (category, created_at DESC)

2) admin_board_comments
   - id          BIGSERIAL PK
   - post_id     BIGINT FK admin_board_posts(id) ON DELETE CASCADE
   - author_id   BIGINT FK users(id) ON DELETE RESTRICT
   - content     TEXT NOT NULL                            (plain text, html.escape 적용 후 저장)
   - created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
   - updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
   - idx_admin_board_comments_post (post_id, created_at ASC)

본문 이미지는 `/static/admin-board-images/<uuid>.<ext>` 형식으로 별도 디스크에 저장되고
content_html 안의 <img src="..."> 로 참조된다(별도 첨부 테이블 없음 — 0030/CS reply 패턴과 동일).

down_revision='0039_user_demo_marketing'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_admin_board"
down_revision = "0039_user_demo_marketing"
branch_labels = None
depends_on = None


_BOARD_POST_STATUSES = ("review", "in_progress", "rejected", "on_hold")


def upgrade() -> None:
    post_status_enum = postgresql.ENUM(
        *_BOARD_POST_STATUSES,
        name="board_post_status_enum",
        create_type=True,
    )
    post_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "admin_board_posts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="board_post_status_enum", create_type=False),
            nullable=False,
            server_default="review",
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
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
            ["author_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_board_posts_status_created "
        "ON admin_board_posts (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_board_posts_category_created "
        "ON admin_board_posts (category, created_at DESC)"
    )

    op.create_table(
        "admin_board_comments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
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
            ["post_id"],
            ["admin_board_posts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_board_comments_post "
        "ON admin_board_comments (post_id, created_at ASC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_admin_board_comments_post")
    op.drop_table("admin_board_comments")

    op.execute("DROP INDEX IF EXISTS idx_admin_board_posts_category_created")
    op.execute("DROP INDEX IF EXISTS idx_admin_board_posts_status_created")
    op.drop_table("admin_board_posts")

    op.execute("DROP TYPE IF EXISTS board_post_status_enum")

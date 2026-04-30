"""rebuild_jobs 테이블 — Story 8.3 FAISS 재빌드 작업 추적."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rebuild_jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "triggered_by_admin_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress_percent", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("stage", sa.String(50), nullable=True),
        sa.Column("target_slot", sa.String(1), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("swapped_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("chunk_count_before", sa.Integer, nullable=True),
        sa.Column("chunk_count_after", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_rebuild_jobs_status", "rebuild_jobs", ["status"])
    op.create_index(
        "idx_rebuild_jobs_created_at",
        "rebuild_jobs",
        [sa.text("created_at DESC")],
    )
    # 동시 active job(queued/running) 1건 제한 — partial unique index on constant (1)
    op.execute(
        "CREATE UNIQUE INDEX uq_rebuild_one_active "
        "ON rebuild_jobs ((1)) WHERE status IN ('queued', 'running')"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_rebuild_one_active")
    op.drop_table("rebuild_jobs")

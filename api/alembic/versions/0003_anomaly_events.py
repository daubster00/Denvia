"""anomaly_events 테이블 생성 — 이상탐지 이벤트 저장소.

Story 1.4 시드 경로: login_brute_force.
Story 6.5에서 이상탐지 전체 완성 예정.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE TYPE IF NOT EXISTS equivalent via DO block (idempotent).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'anomaly_event_type') THEN
                CREATE TYPE anomaly_event_type AS ENUM (
                    'login_brute_force',
                    'rapid_questions',
                    'concurrent_ip_login',
                    'repeated_question',
                    'recovery_abuse'
                );
            END IF;
        END$$
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'anomaly_event_status') THEN
                CREATE TYPE anomaly_event_status AS ENUM (
                    'new',
                    'reviewed',
                    'actioned'
                );
            END IF;
        END$$
        """
    )

    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "login_brute_force",
                "rapid_questions",
                "concurrent_ip_login",
                "repeated_question",
                "recovery_abuse",
                name="anomaly_event_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("target_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("ua", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "new",
                "reviewed",
                "actioned",
                name="anomaly_event_status",
                create_type=False,
            ),
            nullable=False,
            server_default="new",
        ),
        sa.Column("reviewed_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_anomaly_events_type", "anomaly_events", ["type"])
    op.create_index("ix_anomaly_events_target_user_id", "anomaly_events", ["target_user_id"])
    op.create_index("ix_anomaly_events_created_at", "anomaly_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("anomaly_events")
    op.execute("DROP TYPE IF EXISTS anomaly_event_type")
    op.execute("DROP TYPE IF EXISTS anomaly_event_status")

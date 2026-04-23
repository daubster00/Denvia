"""notification_queue 마이그레이션 통합 테스트 — 테이블·컬럼·인덱스 존재 확인."""

import os

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)
DB_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)


@pytest.fixture(scope="module")
def run_migrations():
    """alembic upgrade head를 실행한다 (0001 + 0002)."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_SYNC_URL)
    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


@pytest.mark.asyncio
async def test_notification_queue_table_exists(run_migrations):
    """notification_queue 테이블이 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='notification_queue'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "notification_queue 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_notification_queue_required_columns(run_migrations):
    """notification_queue의 필수 컬럼이 모두 존재하는지 확인한다."""
    required_columns = {
        "id", "user_id", "template_code", "variables", "channel",
        "status", "attempts", "last_error", "idempotency_key",
        "deferred_until", "created_at", "sent_at",
    }
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='notification_queue' AND table_schema='public'"
            )
        )
        columns = {row[0] for row in result.fetchall()}
    await engine.dispose()
    missing = required_columns - columns
    assert not missing, f"누락된 컬럼: {missing}"


@pytest.mark.asyncio
async def test_notification_queue_idempotency_index_exists(run_migrations):
    """멱등성 UNIQUE 인덱스 uq_notification_queue_idempotency가 존재하는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='notification_queue' "
                "AND indexname='uq_notification_queue_idempotency'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "uq_notification_queue_idempotency 인덱스가 존재해야 함"


@pytest.mark.asyncio
async def test_notification_queue_status_deferred_index_exists(run_migrations):
    """발송 처리 복합 인덱스 idx_notification_queue_status_deferred가 존재하는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='notification_queue' "
                "AND indexname='idx_notification_queue_status_deferred'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "idx_notification_queue_status_deferred 인덱스가 존재해야 함"

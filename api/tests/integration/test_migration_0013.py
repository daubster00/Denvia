"""Alembic 0013_payment_tables 마이그레이션 통합 테스트 — Story 3.1.

4테이블 생성 확인, ENUM 값 확인.
실제 DB(postgres 서비스)를 사용한다.
"""

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
    """alembic upgrade head를 실행한다."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_SYNC_URL)
    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


@pytest.mark.asyncio
async def test_subscriptions_table_exists(run_migrations):
    """subscriptions 테이블이 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='subscriptions'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "subscriptions 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_billing_keys_table_exists(run_migrations):
    """billing_keys 테이블이 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='billing_keys'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "billing_keys 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_payments_table_exists(run_migrations):
    """payments 테이블이 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='payments'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "payments 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_payment_events_table_exists(run_migrations):
    """payment_events 테이블이 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='payment_events'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "payment_events 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_subscription_status_enum_values(run_migrations):
    """subscription_status_enum ENUM 값이 올바르게 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT enumlabel FROM pg_enum e "
                "JOIN pg_type t ON e.enumtypid = t.oid "
                "WHERE t.typname = 'subscription_status_enum' "
                "ORDER BY enumsortorder"
            )
        )
        values = [row[0] for row in result.fetchall()]
    await engine.dispose()
    assert set(values) == {"active", "cancel_pending", "canceled", "refund_pending"}


@pytest.mark.asyncio
async def test_payment_status_enum_values(run_migrations):
    """payment_status_enum ENUM 값이 올바르게 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT enumlabel FROM pg_enum e "
                "JOIN pg_type t ON e.enumtypid = t.oid "
                "WHERE t.typname = 'payment_status_enum' "
                "ORDER BY enumsortorder"
            )
        )
        values = [row[0] for row in result.fetchall()]
    await engine.dispose()
    assert set(values) == {"pending", "success", "failed", "refunded", "refund_pending"}


@pytest.mark.asyncio
async def test_payment_events_raw_response_json_is_jsonb(run_migrations):
    """payment_events.raw_response_json 컬럼이 jsonb 타입인지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='payment_events' AND column_name='raw_response_json'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "raw_response_json 컬럼이 존재해야 함"
    assert row[0] == "jsonb", f"raw_response_json 타입이 jsonb여야 하는데 {row[0]}임"


@pytest.mark.asyncio
async def test_payments_unique_order_id_constraint(run_migrations):
    """payments.provider_order_id UNIQUE 제약이 존재하는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='payments' AND indexname='uq_payments_provider_order_id'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "provider_order_id UNIQUE 인덱스가 존재해야 함"

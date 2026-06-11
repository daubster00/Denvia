"""Alembic 0014_billing_customer_key 마이그레이션 통합 테스트 — Story 3.2."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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
    # 0057 admin_grades_dynamic 이후 downgrade base 는 운영 데이터 가드와 충돌한다.
    # 본 fixture 는 격리 DB(예: denvia_test) 사용을 전제로 한다.


@pytest.mark.asyncio
async def test_billing_keys_customer_key_column_exists(run_migrations):
    """billing_keys.customer_key 컬럼이 존재해야 한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='billing_keys' AND column_name='customer_key'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "billing_keys.customer_key 컬럼이 존재해야 함"


@pytest.mark.asyncio
async def test_billing_keys_customer_key_is_nullable(run_migrations):
    """billing_keys.customer_key 컬럼은 nullable이어야 한다 (기존 데이터 호환)."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='billing_keys' AND column_name='customer_key'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None
    assert row[0] == "YES", "customer_key 컬럼은 nullable이어야 함"


@pytest.mark.asyncio
async def test_billing_keys_customer_key_index_exists(run_migrations):
    """idx_billing_keys_customer_key 인덱스가 존재해야 한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='billing_keys' AND indexname='idx_billing_keys_customer_key'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "idx_billing_keys_customer_key 인덱스가 존재해야 함"

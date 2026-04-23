"""Alembic 마이그레이션 통합 테스트.

실제 DB에 upgrade head를 실행하고 users 테이블 + partial index 존재를 확인한다.
CI 환경의 postgres 서비스를 사용한다.
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
    # 테스트 후 롤백 (선택적)
    command.downgrade(alembic_cfg, "base")


@pytest.mark.asyncio
async def test_users_table_exists(run_migrations):
    """users 테이블이 생성되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='users'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "users 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_users_partial_unique_indexes_exist(run_migrations):
    """partial UNIQUE index (uq_users_email, uq_users_phone)가 존재하는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='users' "
                "AND indexname IN ('uq_users_email', 'uq_users_phone')"
            )
        )
        indexes = {row[0] for row in result.fetchall()}
    await engine.dispose()
    assert "uq_users_email" in indexes, "uq_users_email 인덱스가 존재해야 함"
    assert "uq_users_phone" in indexes, "uq_users_phone 인덱스가 존재해야 함"


@pytest.mark.asyncio
async def test_citext_extension_exists(run_migrations):
    """CITEXT 확장이 활성화되었는지 확인한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='citext'")
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "CITEXT 확장이 활성화되어야 함"

"""Alembic 환경 설정 — 비동기 SQLAlchemy 엔진 사용."""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from api.src.models.base import Base

# alembic.ini에서 설정 로드
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 동기 DB URL을 환경변수에서 주입 (Alembic은 동기 연결 사용)
database_sync_url = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)
config.set_main_option("sqlalchemy.url", database_sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 모드 마이그레이션."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """비동기 엔진으로 마이그레이션을 실행한다."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """온라인 모드 마이그레이션."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

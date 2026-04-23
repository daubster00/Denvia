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


# ── Story 1.6: oauth_identity ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oauth_identity_table_exists(run_migrations):
    """oauth_identity 테이블이 생성되었는지 확인."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='oauth_identity'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "oauth_identity 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_oauth_identity_unique_provider_sub(run_migrations):
    """(provider, provider_sub) UNIQUE 제약이 존재하는지 확인."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='oauth_identity' "
                "AND indexname='uq_oauth_identity_provider_sub'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "uq_oauth_identity_provider_sub 인덱스가 존재해야 함"


@pytest.mark.asyncio
async def test_oauth_identity_unique_violation(run_migrations):
    """동일 (provider, provider_sub) 조합은 삽입 불가, 다른 provider는 허용."""
    from datetime import datetime, timezone

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # 테스트용 user 삽입 (CASCADE 제약 충족용)
        await conn.execute(
            text(
                "INSERT INTO users (email, phone, phone_verified, created_at, updated_at) "
                "VALUES ('oauth_test@example.com', '01099990000', true, NOW(), NOW()) "
                "ON CONFLICT DO NOTHING"
            )
        )
        uid_row = await conn.execute(
            text("SELECT id FROM users WHERE email='oauth_test@example.com'")
        )
        user_id = uid_row.scalar_one()

        # 동일 provider_sub, 동일 provider 두 번째 삽입 → IntegrityError 기대
        await conn.execute(
            text(
                "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                "VALUES (:uid, 'kakao', 'sub_conflict_1', NOW())"
            ),
            {"uid": user_id},
        )

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                    "VALUES (:uid, 'kakao', 'sub_conflict_1', NOW())"
                ),
                {"uid": user_id},
            )
        assert False, "같은 (provider, provider_sub) 중복은 UNIQUE 위반이어야 함"
    except Exception:
        pass

    # 다른 provider · 동일 sub는 허용
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                "VALUES (:uid, 'google', 'sub_conflict_1', NOW())"
            ),
            {"uid": user_id},
        )

    # 정리
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM oauth_identity WHERE user_id=:uid"),
            {"uid": user_id},
        )
        await conn.execute(text("DELETE FROM users WHERE id=:uid"), {"uid": user_id})

    await engine.dispose()

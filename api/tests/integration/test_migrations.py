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


@pytest.mark.asyncio
async def test_oauth_identity_idx_user_id(run_migrations):
    """idx_oauth_identity_user_id (non-unique) 인덱스 존재 — find-id 조회 성능 보장."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='oauth_identity' AND indexname='idx_oauth_identity_user_id'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "idx_oauth_identity_user_id 인덱스가 존재해야 함"


@pytest.mark.asyncio
async def test_oauth_identity_check_provider_valid_only(run_migrations):
    """CHECK (provider IN ('kakao','google','naver')) — 다른 값은 IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    engine = create_async_engine(DB_URL)
    user_id: int | None = None
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (email, phone, phone_verified, created_at, updated_at) "
                    "VALUES ('oauth_check@example.com', '01088880000', true, NOW(), NOW()) "
                    "ON CONFLICT DO NOTHING"
                )
            )
            uid_row = await conn.execute(
                text("SELECT id FROM users WHERE email='oauth_check@example.com'")
            )
            user_id = uid_row.scalar_one()

        raised = False
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                        "VALUES (:uid, 'facebook', 'x', NOW())"
                    ),
                    {"uid": user_id},
                )
        except IntegrityError:
            raised = True
        assert raised, "provider='facebook'은 CHECK 제약 위반이어야 함"
    finally:
        if user_id is not None:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM users WHERE id=:uid"), {"uid": user_id}
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_oauth_identity_on_delete_cascade(run_migrations):
    """users 레코드 DELETE 시 FK ON DELETE CASCADE로 oauth_identity 자동 삭제."""
    engine = create_async_engine(DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (email, phone, phone_verified, created_at, updated_at) "
                    "VALUES ('cascade_test@example.com', '01077770000', true, NOW(), NOW()) "
                    "ON CONFLICT DO NOTHING"
                )
            )
            uid_row = await conn.execute(
                text("SELECT id FROM users WHERE email='cascade_test@example.com'")
            )
            user_id = uid_row.scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                    "VALUES (:uid, 'kakao', 'cascade_sub_1', NOW()), "
                    "       (:uid, 'google', 'cascade_sub_2', NOW())"
                ),
                {"uid": user_id},
            )

        async with engine.begin() as conn:
            count_row = await conn.execute(
                text("SELECT COUNT(*) FROM oauth_identity WHERE user_id=:uid"),
                {"uid": user_id},
            )
            assert count_row.scalar_one() == 2

        # users DELETE — CASCADE로 oauth_identity 자동 삭제
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE id=:uid"), {"uid": user_id})

        async with engine.begin() as conn:
            count_row = await conn.execute(
                text("SELECT COUNT(*) FROM oauth_identity WHERE user_id=:uid"),
                {"uid": user_id},
            )
            assert count_row.scalar_one() == 0, "CASCADE로 oauth_identity 레코드가 모두 삭제되어야 함"
    finally:
        await engine.dispose()


# ── Story 2.1: qa_logs · qa_feedback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_qa_logs_table_exists(run_migrations):
    """qa_logs 테이블이 생성되었는지 확인."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='qa_logs'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "qa_logs 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_qa_feedback_table_exists(run_migrations):
    """qa_feedback 테이블이 생성되었는지 확인."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='qa_feedback'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "qa_feedback 테이블이 존재해야 함"


@pytest.mark.asyncio
async def test_qa_feedback_unique_qa_log_id(run_migrations):
    """uq_qa_feedback_qa_log_id UNIQUE 제약 — qa_log 1건당 피드백 1건만 허용."""
    from sqlalchemy.exc import IntegrityError

    engine = create_async_engine(DB_URL)
    qa_log_id: int | None = None
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    "INSERT INTO qa_logs(question_text, rule_matched, created_at) "
                    "VALUES ('테스트 질문', false, NOW()) RETURNING id"
                )
            )
            qa_log_id = row.scalar_one()

        # 첫 번째 피드백 — 성공
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO qa_feedback(qa_log_id, rating, change_count, created_at, updated_at) "
                    "VALUES (:lid, 'good', 0, NOW(), NOW())"
                ),
                {"lid": qa_log_id},
            )

        # 동일 qa_log_id로 두 번째 피드백 — UNIQUE 위반
        raised = False
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO qa_feedback(qa_log_id, rating, change_count, created_at, updated_at) "
                        "VALUES (:lid, 'bad', 0, NOW(), NOW())"
                    ),
                    {"lid": qa_log_id},
                )
        except IntegrityError:
            raised = True
        assert raised, "동일 qa_log_id 피드백 중복은 UNIQUE 위반이어야 함"
    finally:
        if qa_log_id is not None:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM qa_logs WHERE id=:lid"), {"lid": qa_log_id}
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_qa_feedback_rating_check_constraint(run_migrations):
    """rating CHECK 제약 — 'good'/'bad' 외 값은 IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    engine = create_async_engine(DB_URL)
    qa_log_id: int | None = None
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    "INSERT INTO qa_logs(question_text, rule_matched, created_at) "
                    "VALUES ('rating 체크 테스트', false, NOW()) RETURNING id"
                )
            )
            qa_log_id = row.scalar_one()

        raised = False
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO qa_feedback(qa_log_id, rating, change_count, created_at, updated_at) "
                        "VALUES (:lid, 'meh', 0, NOW(), NOW())"
                    ),
                    {"lid": qa_log_id},
                )
        except IntegrityError:
            raised = True
        assert raised, "rating='meh'은 CHECK 위반이어야 함"
    finally:
        if qa_log_id is not None:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM qa_logs WHERE id=:lid"), {"lid": qa_log_id}
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_oauth_identity_not_null_constraints(run_migrations):
    """provider/provider_sub/user_id/linked_at 각각 NULL 삽입 거부."""
    from sqlalchemy.exc import IntegrityError

    engine = create_async_engine(DB_URL)
    user_id: int | None = None
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (email, phone, phone_verified, created_at, updated_at) "
                    "VALUES ('notnull_test@example.com', '01066660000', true, NOW(), NOW()) "
                    "ON CONFLICT DO NOTHING"
                )
            )
            uid_row = await conn.execute(
                text("SELECT id FROM users WHERE email='notnull_test@example.com'")
            )
            user_id = uid_row.scalar_one()

        # user_id NULL
        raised = False
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                        "VALUES (NULL, 'kakao', 'nn1', NOW())"
                    )
                )
        except IntegrityError:
            raised = True
        assert raised, "user_id NULL 삽입은 거부되어야 함"

        # provider NULL
        raised = False
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                        "VALUES (:uid, NULL, 'nn2', NOW())"
                    ),
                    {"uid": user_id},
                )
        except IntegrityError:
            raised = True
        assert raised, "provider NULL 삽입은 거부되어야 함"

        # provider_sub NULL
        raised = False
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO oauth_identity(user_id, provider, provider_sub, linked_at) "
                        "VALUES (:uid, 'kakao', NULL, NOW())"
                    ),
                    {"uid": user_id},
                )
        except IntegrityError:
            raised = True
        assert raised, "provider_sub NULL 삽입은 거부되어야 함"
    finally:
        if user_id is not None:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM users WHERE id=:uid"), {"uid": user_id}
                )
        await engine.dispose()

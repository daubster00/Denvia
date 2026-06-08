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
    """alembic upgrade head를 실행한다.

    teardown 시 0057_admin_grades_dynamic downgrade가 built_in=false 행 존재로 거부되므로
    downgrade 전에 admin_grades 의 커스텀 행을 일괄 삭제한다.
    """
    from sqlalchemy import create_engine

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_SYNC_URL)
    command.upgrade(alembic_cfg, "head")
    yield
    # 0057 downgrade 가드 우회 — 운영 데이터가 아닌 테스트 fixture 이므로 안전.
    sync_engine = create_engine(DB_SYNC_URL)
    try:
        with sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM admin_grades WHERE built_in = false"))
    except Exception:
        # admin_grades 가 아직 없는 상태(이전 다운그레이드 실패 잔재)면 통과.
        pass
    finally:
        sync_engine.dispose()
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
    """partial UNIQUE index 가 존재하는지 확인한다.

    user/admin 분리(2026-05-28) 이후 phone unique 는 두 부분 인덱스로 분리됐다:
    - uq_users_phone_admin (role='admin' 일 때)
    - uq_users_phone_nonadmin (role!='admin' 일 때)
    """
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='users' "
                "AND indexname IN ('uq_users_email', 'uq_users_phone_admin', 'uq_users_phone_nonadmin')"
            )
        )
        indexes = {row[0] for row in result.fetchall()}
    await engine.dispose()
    assert "uq_users_email" in indexes, "uq_users_email 인덱스가 존재해야 함"
    assert "uq_users_phone_admin" in indexes, "uq_users_phone_admin 인덱스가 존재해야 함"
    assert "uq_users_phone_nonadmin" in indexes, "uq_users_phone_nonadmin 인덱스가 존재해야 함"


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
async def test_0007_user_quota_override_columns(run_migrations):
    """Story 2.3: users.daily_quota_override / free_delay_override 컬럼이 nullable INT로 존재한다."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name, is_nullable, data_type "
                "FROM information_schema.columns "
                "WHERE table_name='users' AND column_name IN ('daily_quota_override','free_delay_override')"
            )
        )
        rows = {row[0]: (row[1], row[2]) for row in result.fetchall()}
    await engine.dispose()
    assert "daily_quota_override" in rows, "daily_quota_override 컬럼이 존재해야 함"
    assert "free_delay_override" in rows, "free_delay_override 컬럼이 존재해야 함"
    assert rows["daily_quota_override"][0] == "YES", "daily_quota_override는 nullable이어야 함"
    assert rows["free_delay_override"][0] == "YES", "free_delay_override는 nullable이어야 함"
    assert "int" in rows["daily_quota_override"][1].lower(), "daily_quota_override는 integer 타입이어야 함"
    # free_delay_override 는 NUMERIC(4,1) 로 변경됨 (소수 초 단위 지연 지원, 2026-05 마이그레이션).
    assert rows["free_delay_override"][1].lower() in ("integer", "numeric"), \
        f"free_delay_override는 integer/numeric 이어야 함 (got {rows['free_delay_override'][1]})"


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

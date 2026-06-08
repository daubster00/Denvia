"""Story 10.1 — admin_grade 마이그레이션 결과 통합 검증.

전제: dev DB 가 이미 0055_admin_grade_page_permissions 까지 적용된 상태에서 실행한다.
(make api-upgrade 또는 alembic upgrade head 후 실행)

검증 대상:
1) admin_grade_enum 타입 + 4개 값 존재
2) users 테이블에 admin_grade·admin_blocked_until·admin_block_reason·admin_signup_at 컬럼 존재
3) admin_grade_page_permissions 테이블 + UNIQUE(admin_grade, page_route) 존재 (0055 에서 0054 의 user-level 테이블 대체)
4) partial UNIQUE 인덱스 uq_admin_grade_master 존재 + 두 번째 master INSERT 실패(rollback)
5) 백필 결과: role='admin' AND admin_grade='master' 행 수 = 0 또는 1

테이블을 drop 하지 않는다 — 모든 INSERT 는 트랜잭션 안에서 ROLLBACK.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)


@pytest.mark.asyncio
async def test_admin_grade_enum_타입_4값_존재():
    """0057 — admin_grade 값은 pg_enum 이 아니라 admin_grades 테이블의 row 로 관리한다.
    내장 등급 4종(master/operator/sub_operator/pending) 이 모두 존재해야 한다.
    """
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT code FROM admin_grades"))
        values = [row[0] for row in result.fetchall()]
    await engine.dispose()
    # is_builtin 플래그 차이가 있을 수 있으나, 4종 코드 자체는 모두 row 로 존재해야 한다.
    assert {"master", "operator", "sub_operator", "pending"} <= set(values)


@pytest.mark.asyncio
async def test_users_에_admin_grade_컬럼_4종_존재():
    expected = {"admin_grade", "admin_blocked_until", "admin_block_reason", "admin_signup_at"}
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users' AND column_name = ANY(:cols)"
            ),
            {"cols": list(expected)},
        )
        actual = {row[0] for row in result.fetchall()}
    await engine.dispose()
    assert actual == expected


@pytest.mark.asyncio
async def test_admin_grade_page_permissions_테이블_존재_및_UNIQUE_제약():
    """0055 — user-level 테이블을 등급-level 매트릭스 테이블로 교체했음을 검증."""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        # 새 테이블 존재
        tbl = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='admin_grade_page_permissions'"
            )
        )
        assert tbl.fetchone() is not None

        # 옛 테이블은 사라져야 함
        old_tbl = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename='admin_page_permissions'"
            )
        )
        assert old_tbl.fetchone() is None

        # UNIQUE 제약 (admin_grade, page_route)
        uniq = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname='uq_admin_grade_page_permissions'"
            )
        )
        assert uniq.fetchone() is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_partial_unique_index_uq_admin_grade_master_존재():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname='uq_admin_grade_master'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None
    # WHERE 조건이 partial UNIQUE 인지 확인
    assert "admin_grade" in row[0]
    assert "master" in row[0]
    assert "withdrawn_at" in row[0]


@pytest.mark.asyncio
async def test_master_등급_2명_동시_활성_INSERT_unique_violation():
    """기존 마스터가 있든 없든, 같은 트랜잭션 안에서 활성 master 2개를 만들면 실패해야 한다.

    트랜잭션을 ROLLBACK 으로 끝내므로 dev DB 상태에 영향이 없다.
    """
    engine = create_async_engine(DB_URL)
    raised = False
    try:
        async with engine.begin() as conn:  # 자동 commit/rollback
            # 기존 master 가 있으면 임시 해제 (트랜잭션 안에서만 유효)
            await conn.execute(
                text(
                    "UPDATE users SET admin_grade='operator' "
                    "WHERE admin_grade='master' AND withdrawn_at IS NULL"
                )
            )
            # 동일 트랜잭션에서 신규 master 2개 INSERT 시도
            await conn.execute(
                text(
                    "INSERT INTO users (email, role, admin_grade, "
                    "subscription_status, phone_verified, must_reset_password, "
                    "pro_granted_by_admin, created_at, updated_at) "
                    "VALUES ('rbac_test_master1@example.test', 'admin', 'master', "
                    "'free', false, false, false, NOW(), NOW())"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO users (email, role, admin_grade, "
                    "subscription_status, phone_verified, must_reset_password, "
                    "pro_granted_by_admin, created_at, updated_at) "
                    "VALUES ('rbac_test_master2@example.test', 'admin', 'master', "
                    "'free', false, false, false, NOW(), NOW())"
                )
            )
            # 정상 동작이면 여기 도달하지 않음 — 강제 실패
            raise AssertionError("두 번째 master INSERT 는 실패해야 한다")
    except IntegrityError as e:
        # partial UNIQUE 위반 → 23505
        raised = True
        assert "uq_admin_grade_master" in str(e) or "unique" in str(e).lower()
    finally:
        await engine.dispose()
    assert raised, "IntegrityError 가 발생해야 한다"


@pytest.mark.asyncio
async def test_백필_결과_master_0_또는_1개():
    """ADR-0001 편차 #6 (g) 항 백필 검증.

    btmdesign@naver.com 이 시드되어 있으면 master 1개, 없으면 0개.
    어느 쪽이든 admin_grade IS NULL 인 활성 admin 은 없어야 한다(백필 완료).
    """
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        master_count = await conn.execute(
            text(
                "SELECT COUNT(*) FROM users "
                "WHERE role='admin' AND admin_grade='master' AND withdrawn_at IS NULL"
            )
        )
        masters = master_count.scalar_one()

        null_admin_count = await conn.execute(
            text(
                "SELECT COUNT(*) FROM users "
                "WHERE role='admin' AND admin_grade IS NULL AND withdrawn_at IS NULL"
            )
        )
        nulls = null_admin_count.scalar_one()
    await engine.dispose()
    assert masters in (0, 1), f"master 활성 행 수가 0 또는 1 이어야 함: {masters}"
    assert nulls == 0, f"백필 누락 admin 이 없어야 함: {nulls}"

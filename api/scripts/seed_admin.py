"""관리자 초기 계정 삽입 스크립트 — 멱등 보장 (이미 존재하면 skip)."""

import asyncio
import os
import sys
from datetime import UTC, datetime

from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.src.settings import settings  # noqa: E402

ph = PasswordHasher()


async def seed_admin() -> None:
    admin_email = os.environ.get("DENVIA_ADMIN_EMAIL", settings.denvia_admin_email)
    admin_password = os.environ.get(
        "DENVIA_ADMIN_INITIAL_PASSWORD", settings.denvia_admin_initial_password
    )

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # 이미 admin 계정이 존재하면 skip
        result = await session.execute(
            text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        )
        existing = result.fetchone()
        if existing:
            print(  # noqa: E501
                f"[seed_admin] admin 계정이 이미 존재합니다 (id={existing[0]}). skip."
            )
            await engine.dispose()
            return

        # argon2id 해시 생성
        password_hash = ph.hash(admin_password)
        now = datetime.now(UTC)

        await session.execute(
            text(
                """
                INSERT INTO users
                  (email, password_hash, role, subscription_status,
                   phone_verified, must_reset_password, created_at, updated_at)
                VALUES
                  (:email, :password_hash, 'admin', 'free',
                   false, false, :now, :now)
                """
            ),
            {"email": admin_email, "password_hash": password_hash, "now": now},
        )
        await session.commit()
        print(f"[seed_admin] admin 계정 생성 완료: {admin_email}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_admin())

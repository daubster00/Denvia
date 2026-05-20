"""KillswitchService — 자동(auto_free_only)·수동(manual_total) 양립 모드.

Story 5.2: 자동 모드 INSERT/해제는 budget_tasks.check_thresholds 가 담당.
Story 9.2: 수동 모드 발동·해제 + 통합 status 조회 헬퍼 추가.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.killswitch_state import (
    KillswitchState,
    MODE_AUTO_FREE_ONLY,
    MODE_MANUAL_TOTAL,
)
from api.src.models.user import User
from api.src.services import runtime_config_service
from api.src.services.budget_service import get_current_month_snapshot

logger = structlog.get_logger(__name__)


# ── 도메인 예외 ─────────────────────────────────────────────────────────────


class KillSwitchAlreadyActive(Exception):
    """이미 활성화된 모드를 다시 발동하려 할 때 발생 (409 매핑)."""


class KillSwitchNotActive(Exception):
    """활성 상태가 아닌 모드를 해제하려 할 때 발생 (409 매핑)."""


# ── 기존 헬퍼 (Story 5.2) ─────────────────────────────────────────────────────


async def get_active_modes(session: AsyncSession) -> set[str]:
    rows = (await session.execute(
        select(KillswitchState.mode).where(KillswitchState.deactivated_at.is_(None))
    )).scalars().all()
    return set(rows)


async def is_auto_free_only_active(session: AsyncSession) -> bool:
    return MODE_AUTO_FREE_ONLY in await get_active_modes(session)


async def is_any_total_block_active(session: AsyncSession) -> bool:
    return MODE_MANUAL_TOTAL in await get_active_modes(session)


# ── Story 9.2 신규 헬퍼 ──────────────────────────────────────────────────────


def _mask_email(email: str | None) -> str | None:
    """Story 6.4 _mask_email 패턴 — local의 처음 2자만 노출."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local}****@{domain}"
    return f"{local[:2]}****@{domain}"


@dataclass(frozen=True)
class DeactivationResult:
    """수동 해제 결과 — 응답 스키마용."""

    killswitch_state_id: int
    activated_at: datetime
    deactivated_at: datetime
    duration_seconds: int


async def get_status(
    session: AsyncSession,
    redis_runtime: aioredis.Redis | None = None,
) -> dict[str, Any]:
    """auto_free_only / manual_total 두 모드의 현재 상태를 조합해 반환한다.

    - auto_free_only: budget_service.get_current_month_snapshot 결합 (percent / limit / spent).
      redis_runtime 주입 시 USD→KRW 환산 보조 필드(monthly_limit_krw, spent_krw, usd_to_krw)도
      포함한다 (전체 시스템 KRW 통일). 미주입 시 기본 환율(1400) 사용.
    - manual_total: activated_by_admin_email은 _mask_email 마스킹.
    비활성 모드의 시각·사유 필드는 모두 None.
    """
    snapshot = await get_current_month_snapshot(session)

    if redis_runtime is not None:
        usd_to_krw = await runtime_config_service.get_usd_to_krw(redis_runtime)
    else:
        usd_to_krw = runtime_config_service.DEFAULT_USD_TO_KRW
    monthly_limit_krw = int(
        (snapshot.monthly_limit_usd * Decimal(usd_to_krw)).quantize(Decimal("1"))
    )
    spent_krw = int(
        (snapshot.spent_usd * Decimal(usd_to_krw)).quantize(Decimal("1"))
    )

    auto_row = (await session.execute(
        select(KillswitchState).where(
            KillswitchState.mode == MODE_AUTO_FREE_ONLY,
            KillswitchState.deactivated_at.is_(None),
        ).limit(1)
    )).scalar_one_or_none()

    manual_row = (await session.execute(
        select(KillswitchState).where(
            KillswitchState.mode == MODE_MANUAL_TOTAL,
            KillswitchState.deactivated_at.is_(None),
        ).limit(1)
    )).scalar_one_or_none()

    auto_block: dict[str, Any]
    if auto_row is None:
        auto_block = {
            "active": False,
            "activated_at": None,
            "year_month": snapshot.year_month,
            "current_percent": snapshot.percent,
            "monthly_limit_usd": snapshot.monthly_limit_usd,
            "spent_usd": snapshot.spent_usd,
            "monthly_limit_krw": monthly_limit_krw,
            "spent_krw": spent_krw,
            "usd_to_krw": usd_to_krw,
        }
    else:
        auto_block = {
            "active": True,
            "activated_at": auto_row.activated_at,
            # 0028 직후 기존 row의 year_month는 NULL — snapshot.year_month로 폴백.
            "year_month": auto_row.year_month or snapshot.year_month,
            "current_percent": snapshot.percent,
            "monthly_limit_usd": snapshot.monthly_limit_usd,
            "spent_usd": snapshot.spent_usd,
            "monthly_limit_krw": monthly_limit_krw,
            "spent_krw": spent_krw,
            "usd_to_krw": usd_to_krw,
        }

    manual_block: dict[str, Any]
    if manual_row is None:
        manual_block = {
            "active": False,
            "activated_at": None,
            "deactivated_at": None,
            "reason": None,
            "activated_by_admin_email": None,
            "activated_by_admin_id": None,
        }
    else:
        admin_email: str | None = None
        if manual_row.activated_by is not None:
            admin = (await session.execute(
                select(User.email).where(User.id == manual_row.activated_by)
            )).scalar_one_or_none()
            admin_email = _mask_email(admin)
        manual_block = {
            "active": True,
            "activated_at": manual_row.activated_at,
            "deactivated_at": None,
            "reason": manual_row.reason,
            "activated_by_admin_email": admin_email,
            "activated_by_admin_id": manual_row.activated_by,
        }

    return {"auto_free_only": auto_block, "manual_total": manual_block}


async def activate_manual(
    session: AsyncSession,
    *,
    admin_id: int,
    reason: str,
) -> KillswitchState:
    """manual_total 발동 — partial UNIQUE 위반 시 KillSwitchAlreadyActive.

    동시성 방어: 조회는 with_for_update 안 함(존재 여부만), 실제 직렬화는
    uq_killswitch_active_mode partial UNIQUE 제약이 보장.
    """
    existing = (await session.execute(
        select(KillswitchState).where(
            KillswitchState.mode == MODE_MANUAL_TOTAL,
            KillswitchState.deactivated_at.is_(None),
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        raise KillSwitchAlreadyActive(
            f"manual_total already active (id={existing.id})"
        )

    row = KillswitchState(
        mode=MODE_MANUAL_TOTAL,
        activated_by=admin_id,
        reason=reason,
        year_month=None,  # manual_total은 year_month 무관
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        # 동시 INSERT race — partial UNIQUE 위반.
        await session.rollback()
        raise KillSwitchAlreadyActive("manual_total already active (race)") from exc
    return row


async def deactivate_manual(
    session: AsyncSession,
    *,
    admin_id: int,
) -> DeactivationResult:
    """manual_total 해제 — with_for_update로 단일 활성 row 잠금 후 UPDATE."""
    row = (await session.execute(
        select(KillswitchState)
        .where(
            KillswitchState.mode == MODE_MANUAL_TOTAL,
            KillswitchState.deactivated_at.is_(None),
        )
        .with_for_update()
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise KillSwitchNotActive("manual_total not active")

    now = datetime.now(timezone.utc)
    row.deactivated_at = now
    row.deactivated_by = admin_id
    await session.flush()

    activated_at = row.activated_at
    if activated_at.tzinfo is None:
        activated_at = activated_at.replace(tzinfo=timezone.utc)
    duration = now - activated_at
    return DeactivationResult(
        killswitch_state_id=row.id,
        activated_at=activated_at,
        deactivated_at=now,
        duration_seconds=int(duration.total_seconds()),
    )


async def publish_killswitch_event(redis, payload: dict[str, Any]) -> None:
    """admin:events 채널에 killswitch_status 이벤트를 publish한다.

    실패해도 라우터 응답에 영향 없음 — 로그만 남김 (budget_tasks _publish 패턴).
    """
    try:
        await redis.publish("admin:events", json.dumps(payload, default=str))
    except Exception:
        logger.error("killswitch.redis_publish_failed", payload=payload, exc_info=True)

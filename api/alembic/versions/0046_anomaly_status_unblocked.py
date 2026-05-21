"""anomaly_event_status enum 에 'unblocked' 값 추가.

배경:
- 관리자가 이상탐지 UI 에서 차단을 해제한 경우, 해당 이벤트 행에 '차단 해제됨' 상태를
  남겨 차단/해제 이력을 한눈에 보여줘야 한다.
- 기존 'actioned' 상태는 '차단 적용됨' 의미. 해제 시 다시 'actioned' 가 아닌 별도
  종결 상태가 필요하다. 'unblocked' 도달 행은 액션 버튼(24h/7d/영구) 을 다시 노출한다.

ENUM 값 추가는 idempotent. Postgres 는 트랜잭션 안에서 ALTER 후 즉시 사용이 불가하므로
autocommit_block 사용 (0044 와 동일 패턴).

down_revision='0045_experience_annual_increment'.
"""

from __future__ import annotations

from alembic import op


revision = "0046_anomaly_status_unblocked"
down_revision = "0045_experience_annual_increment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE anomaly_event_status ADD VALUE IF NOT EXISTS 'unblocked'"
        )


def downgrade() -> None:
    # ENUM 값 제거는 Postgres 에서 비파괴적 다운그레이드가 불가능 — 빈 값으로 남겨둔다.
    pass

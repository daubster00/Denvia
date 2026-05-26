"""anomaly_event_type enum 에 'sms_abuse' 값 추가.

배경:
- 휴대폰 인증(/auth/sms/send) 호출이 1시간 안에 10회 이상이면 봇/공격 패턴으로 보고
  24시간 동안 동일 번호의 send/verify 를 거절한다.
- 이상탐지 리스트(/admin/anomaly)에서 추적할 수 있도록 anomaly_event_type 에 'sms_abuse'
  값을 추가한다.

ENUM 값 추가는 idempotent — Postgres 의 ALTER TYPE ... ADD VALUE IF NOT EXISTS 패턴을
0044/0046 과 동일하게 autocommit_block 안에서 실행한다.

down_revision='0052_login_events'.
"""

from __future__ import annotations

from alembic import op


revision = "0053_anomaly_sms_abuse"
down_revision = "0052_login_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE anomaly_event_type ADD VALUE IF NOT EXISTS 'sms_abuse'"
        )


def downgrade() -> None:
    # ENUM 값 제거는 Postgres 에서 비파괴적 다운그레이드가 불가능 — 빈 값으로 남겨둔다.
    pass

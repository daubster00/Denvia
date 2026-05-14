"""Story 9.1 v1.1 후속 — payment_events.refund_kind ENUM 컬럼 신설.

ADR-0001 편차 #5 환불 정책 v1.1의 후속 패치. 운영 환불(Story 9.1 v1.1
`admin_payment_service`)과 청약철회(Story 3.6 v1.1 `billing_service._execute_cooling_off_refund`)
양쪽에서 `payment_events.raw_response_json` JSONB 안에 인라인으로 보관해 온
`refund_kind` 분류 메타를 전용 ENUM 컬럼으로 승격한다.

- 값 3종:
    * `manual_full`        — 관리자 운영 환불 단발 전액 (sequence=1 AND 전액)
    * `manual_partial`     — 관리자 운영 환불 부분 또는 다회 누적 (sequence>=1)
    * `cooling_off`        — 7일 이내 청약철회 자동 전액
- 컬럼은 NULL 허용. `charge_*` / `retry_scheduled` / `refund_requested` 이벤트는
  분류 대상이 아니므로 NULL로 남는다. 따라서 CHECK 제약은 두지 않는다.
- 부분 인덱스 `idx_payment_events_refund_kind` 는 NULL이 아닌 행만 색인 — 관리자
  재무 분석 화면에서 환불 종류별 집계 시 사용.

백필 전략:
- 기존 `raw_response_json->>'refund_kind'` 값이 신규 enum 3종과 일치하는 행만
  새 컬럼으로 복사한다. 값이 없거나 enum 밖이면 NULL 유지.
- raw_response_json은 그대로 둔다 — 양방향 호환을 한 사이클 유지하고
  후속 클린업 마이그레이션에서 JSONB 키 삭제를 검토한다.

down_revision='0034_drop_manual_refund_queue'.
"""

from __future__ import annotations

from alembic import op

revision = "0035_payment_events_refund_kind"
down_revision = "0034_drop_manual_refund_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. enum 타입 생성
    op.execute(
        "CREATE TYPE refund_kind_enum AS ENUM ("
        "'manual_full', 'manual_partial', 'cooling_off')"
    )

    # 2. 컬럼 추가 (NULL 허용)
    op.execute(
        "ALTER TABLE payment_events "
        "ADD COLUMN refund_kind refund_kind_enum NULL"
    )

    # 3. 부분 인덱스 — NULL이 아닌 행만 색인
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_payment_events_refund_kind "
        "ON payment_events (refund_kind) WHERE refund_kind IS NOT NULL"
    )

    # 4. 백필 — JSONB->>'refund_kind' 값이 신규 enum 3종이면 복사
    op.execute(
        "UPDATE payment_events "
        "SET refund_kind = (raw_response_json->>'refund_kind')::refund_kind_enum "
        "WHERE event_type IN ('refund_success', 'refund_denied') "
        "  AND raw_response_json IS NOT NULL "
        "  AND raw_response_json->>'refund_kind' "
        "      IN ('manual_full', 'manual_partial', 'cooling_off')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_payment_events_refund_kind")
    op.execute("ALTER TABLE payment_events DROP COLUMN IF EXISTS refund_kind")
    op.execute("DROP TYPE IF EXISTS refund_kind_enum")

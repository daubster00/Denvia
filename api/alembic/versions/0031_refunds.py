"""Story 9.1 v1.1 — refunds 테이블 (관리자 운영 환불 부분/전액).

ADR-0001 편차 #5 환불 정책 v1.1 — 관리자가 결제 건 단위로 직접 금액 입력형
환불을 처리할 수 있도록 시계열 환불 row 보존 테이블을 신설한다.

테이블 구조:
- id BIGSERIAL PK
- payment_id BIGINT FK→payments.id ON DELETE RESTRICT NOT NULL
- admin_id BIGINT FK→users.id ON DELETE RESTRICT NOT NULL  (환불을 처리한 관리자)
- cancel_amount INT NOT NULL                  (이번 환불 금액)
- original_payment_amount INT NOT NULL        (결제 시점 원금 스냅샷 — payments 변경 영향 받지 않도록)
- prorated_suggestion INT NULL                (참고 일할 권장값 스냅샷; 강제 아님)
- reason_category refund_reason_category_enum NOT NULL  (5종)
- memo TEXT NULL                              (관리자 자유 메모; 최대 500자 — 서비스 레이어 검증)
- refund_sequence INT NOT NULL                (동일 결제 내 N번째 환불, 1부터)
- toss_response_json JSONB NOT NULL           (PG 응답 원문 보존 — reconcile용)
- idempotency_key VARCHAR(200) NOT NULL       (refund:{payment_id}:manual:{refund_sequence})
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
- updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

CHECK 3종:
1. cancel_amount > 0          음수·0 차단
2. refund_sequence >= 1        1부터
3. cancel_amount <= original_payment_amount   단일 row가 원금 초과 차단
   (누적 검증은 admin_payment_service 책임)

UNIQUE 2종:
1. (payment_id, refund_sequence)   동일 결제의 동일 sequence 중복 방지(idempotent race 차단)
2. idempotency_key 단일             notification 시스템·외부 retry 안전

INDEX 2종:
1. (payment_id)                    AC-15 잔액 계산 조회용
2. (admin_id, created_at)          관리자별 환불 이력 조회용

Story 3.6 v1.1(청약철회)도 향후 본 테이블에 row를 INSERT하도록 확장 가능하나,
Phase 1 시점에서는 청약철회는 raw_response_json 인라인 메타로 처리. Phase 2 또는 후속
패치에서 청약철회도 동일 테이블에 INSERT(`reason_category` 신규 enum 값 또는
별도 컬럼 도입 검토).

down_revision='0030_inquiry_board'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_refunds"
down_revision = "0030_inquiry_board"
branch_labels = None
depends_on = None


_REFUND_REASON_CATEGORIES = (
    "customer_complaint",
    "duplicate_payment",
    "system_error",
    "special_mid_cancel",
    "other",
)


def upgrade() -> None:
    # 1. enum 정의
    op.execute(
        "CREATE TYPE refund_reason_category_enum AS ENUM ("
        "'customer_complaint', 'duplicate_payment', 'system_error', "
        "'special_mid_cancel', 'other')"
    )

    # 2. refunds 테이블 생성
    op.create_table(
        "refunds",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "payment_id",
            sa.BigInteger,
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "admin_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cancel_amount", sa.Integer, nullable=False),
        sa.Column("original_payment_amount", sa.Integer, nullable=False),
        sa.Column("prorated_suggestion", sa.Integer, nullable=True),
        sa.Column(
            "reason_category",
            postgresql.ENUM(
                *_REFUND_REASON_CATEGORIES,
                name="refund_reason_category_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("memo", sa.Text, nullable=True),
        sa.Column("refund_sequence", sa.Integer, nullable=False),
        sa.Column("toss_response_json", postgresql.JSONB, nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 3. CHECK 제약 3종
    op.create_check_constraint(
        "ck_refunds_cancel_amount_positive",
        "refunds",
        "cancel_amount > 0",
    )
    op.create_check_constraint(
        "ck_refunds_refund_sequence_positive",
        "refunds",
        "refund_sequence >= 1",
    )
    op.create_check_constraint(
        "ck_refunds_amount_le_original",
        "refunds",
        "cancel_amount <= original_payment_amount",
    )

    # 4. UNIQUE 제약 2종
    op.create_unique_constraint(
        "uq_refunds_payment_sequence",
        "refunds",
        ["payment_id", "refund_sequence"],
    )
    op.create_unique_constraint(
        "uq_refunds_idempotency_key",
        "refunds",
        ["idempotency_key"],
    )

    # 5. 인덱스 2종
    op.create_index("idx_refunds_payment_id", "refunds", ["payment_id"])
    op.create_index(
        "idx_refunds_admin_id_created_at",
        "refunds",
        ["admin_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_refunds_admin_id_created_at", table_name="refunds")
    op.drop_index("idx_refunds_payment_id", table_name="refunds")
    op.drop_constraint("uq_refunds_idempotency_key", "refunds", type_="unique")
    op.drop_constraint("uq_refunds_payment_sequence", "refunds", type_="unique")
    op.drop_constraint("ck_refunds_amount_le_original", "refunds", type_="check")
    op.drop_constraint("ck_refunds_refund_sequence_positive", "refunds", type_="check")
    op.drop_constraint("ck_refunds_cancel_amount_positive", "refunds", type_="check")
    op.drop_table("refunds")
    op.execute("DROP TYPE IF EXISTS refund_reason_category_enum")

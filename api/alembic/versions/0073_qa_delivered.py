"""#141 qa_logs.delivered — 완성 답변이 사용자에게 전송 완료됐는지 여부.

배경: 답변 생성은 취소 불가능한 백그라운드 스레드가 끝까지 만든다. 유저와 연결이
끊겨도 그 완성 답변을 DB에 저장(status=completed, delivered=false)해 두고, 사용자가
다시 시도하면 저장분을 차감 없이 그대로 재생한다.

- delivered=true : 답변을 사용자에게 정상 전송 완료(재생 대상 아님)
- delivered=false: 완성됐지만 전송 못 함(연결 끊김 등) → 재시도 시 재생 대상

additive — server_default false. 기존 행은 false 로 채워지지만, 오래된 행은 재생
조건(created_at 최근 + 질문 일치)에서 자연히 걸러진다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0073_qa_delivered"
down_revision = "0072_qa_device_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_logs",
        sa.Column(
            "delivered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("qa_logs", "delivered")

"""#141 qa_logs.device_type — 접속 기기(mobile/pc/unknown) 기록.

연결 끊김 오류가 어느 디바이스에서 나는지 진단하기 위해, 질의 시작 시점의
User-Agent 로 기기 종류를 판별해 저장한다. 요청 시작 시(INSERT 시점) 채워지므로,
끊겨서 유령이 된(status=error) 행에도 디바이스가 남는다.

additive nullable 컬럼 — 기존 데이터/제약 변경 없음.
"""
import sqlalchemy as sa
from alembic import op

revision = "0072_qa_device_type"
down_revision = "0071_qa_review_admin_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_logs",
        sa.Column("device_type", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("qa_logs", "device_type")

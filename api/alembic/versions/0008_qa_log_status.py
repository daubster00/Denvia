"""qa_logs 테이블에 status 컬럼 추가 — Story 2.5 Conversation Reset.

status: 스트림 완료 상태 추적. NULL = 마이그레이션 이전 행(레거시).
  - 'in_progress' : 스트림 시작 시 Python 기본값 (서버 기본값은 NULL)
  - 'completed'   : 정상 done 이벤트 발행 완료
  - 'aborted'     : 클라이언트 단절(GeneratorExit) — F-306 초기화 포함
  - 'error'       : tenacity 최종 실패 또는 내부 예외

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_logs",
        sa.Column("status", sa.String(16), nullable=True),
    )
    # nullable이므로 기존 행은 NULL 유지 — misleading default 금지


def downgrade() -> None:
    op.drop_column("qa_logs", "status")

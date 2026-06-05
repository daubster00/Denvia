"""users 테이블에 login_locked_until 컬럼 추가.

배경:
- 로그인 잠금(brute-force lockout)은 Redis TTL 기반으로 자동 만료되나,
  만료 시각을 DB에 기록해 두지 않아 배치가 만료 감지 후 사용자 쪽지 발송 불가.
- login_locked_until 에 잠금 만료 시각을 기록 → expire_blocks 배치가
  만료 시점에 InboxMessage 자동 발송.

down_revision='0058_warmup_feature_perm'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059_login_locked_until"
down_revision = "0058_warmup_feature_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("login_locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "login_locked_until")

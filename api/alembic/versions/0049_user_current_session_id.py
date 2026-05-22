"""users.current_session_id — 동일 계정 단일 세션(later wins) 추적용.

배경:
- 동일 계정으로 다른 위치에서 다시 로그인하면 새 세션을 살리고 이전 세션은 즉시
  무효화한다. 이전 세션 쿠키로 들어오는 요청은 401 AUTH_SESSION_SUPERSEDED 로 거부
  되고 프론트는 "다른 장소에서 로그인되어 로그아웃되었습니다" 모달을 표시한다.
- 구현: 로그인 시점에 64자 이내 nonce(secrets.token_urlsafe(24))를 발급해
  users.current_session_id 에 저장하고 JWT 의 `sid` 클레임에 동일 값을 박는다.
  매 요청에서 두 값을 비교한다.

NULL=현재 활성 세션 없음(가입 직전·로그아웃 직후·기존 사용자 초기 상태).

down_revision='0048_anomaly_drawer_cols'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0049_user_current_session_id"
down_revision = "0048_anomaly_drawer_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("current_session_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "current_session_id")

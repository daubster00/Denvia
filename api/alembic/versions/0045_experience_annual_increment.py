"""users.experience_last_increment_year 컬럼 — 연차 매년 1월 1일 자동 +1 가산.

정책:
- 매년 1월 1일 00:05 KST 배치(`career_tasks.annual_increment`)가 모든 회원의
  years_of_experience 를 +1 누적한다.
- 멱등성 보장 — `experience_last_increment_year < <올해 KST 연도>` 인 행만 갱신하고
  갱신 후 같은 컬럼을 올해 KST 연도로 셋. 같은 해에 두 번 실행돼도 0건.
- catch-up — 배치가 한 해 누락되면 다음 실행 시 (올해 - 마지막연도) 만큼 한 번에 가산.
  현재 정책상 한 해 한 번 +1이므로 catch-up 의미는 운영 사고 대비.

백필 정책 (PRD 결정 — '지금부터 시작'):
- 기존 회원의 experience_last_increment_year 를 *현재 KST 연도*로 채운다.
- 즉 다음 1월 1일에 일제히 +1 된다. 기존 회원의 가입연도 차이 보정은 수행하지 않는다.
- years_of_experience IS NULL 행(student_other / 미설정)은 NULL 유지.

down_revision='0044_anomaly_throttle'.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_experience_annual_increment"
down_revision = "0044_anomaly_throttle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("experience_last_increment_year", sa.SmallInteger(), nullable=True),
    )
    # 기존 회원 백필 — '지금부터 시작' 정책.
    # 다음 1월 1일에 일제히 +1 되도록 현재 KST 연도를 기록.
    op.execute(
        "UPDATE users "
        "SET experience_last_increment_year = "
        "    EXTRACT(YEAR FROM (NOW() AT TIME ZONE 'Asia/Seoul'))::SMALLINT "
        "WHERE years_of_experience IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "experience_last_increment_year")

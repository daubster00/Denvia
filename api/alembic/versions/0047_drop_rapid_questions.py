"""rapid_questions anomaly 타입 완전 폐기.

배경:
- rapid_followup_questions (답변 직후 3초 이내 연속 질의) 와 성격이 중복돼
  2026-05-21 부로 ``check_rapid_questions`` hook 호출을 이미 비활성화함.
- 본 마이그레이션은 잔존 코드 정리 후속 — DB 단에서도 rapid_questions 기록과
  enum 값을 모두 제거한다.

순서:
1. 잔존 anomaly_events 행 DELETE (type='rapid_questions').
2. Postgres ENUM 값 제거 — ALTER TYPE ... DROP VALUE 가 지원되지 않으므로
   새 ENUM 타입을 만들고 컬럼을 교체한 뒤 옛 타입을 DROP 하는 표준 패턴 사용.

down_revision='0046_anomaly_status_unblocked'.
"""

from __future__ import annotations

from alembic import op


revision = "0047_drop_rapid_questions"
down_revision = "0046_anomaly_status_unblocked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 잔존 데이터 삭제.
    op.execute("DELETE FROM anomaly_events WHERE type = 'rapid_questions'")

    # 1-b) 백필 — 사용자관리 페이지에서 차단 해제된 사용자의 'actioned' anomaly 가
    # 'unblocked' 로 동기화되지 않은 채 남아 있다(0046 이전 동작). 이번 unblock 동기화
    # 코드 진입 전에 만들어진 stale 행을 일괄 정리한다.
    op.execute(
        """
        UPDATE anomaly_events
        SET status = 'unblocked'
        WHERE status = 'actioned'
          AND target_user_id IS NOT NULL
          AND target_user_id IN (
              SELECT id FROM users WHERE subscription_status != 'blocked'
          )
        """
    )

    # 2) 새 ENUM 타입 생성 — rapid_questions 제외.
    op.execute(
        """
        CREATE TYPE anomaly_event_type_new AS ENUM (
            'login_brute_force',
            'concurrent_ip_login',
            'repeated_question',
            'recovery_abuse',
            'rapid_followup_questions'
        )
        """
    )

    # 3) 컬럼 타입 교체 (USING text 캐스팅으로 기존 값 보존).
    op.execute(
        """
        ALTER TABLE anomaly_events
        ALTER COLUMN type TYPE anomaly_event_type_new
        USING type::text::anomaly_event_type_new
        """
    )

    # 4) 옛 타입 DROP + 새 타입 rename.
    op.execute("DROP TYPE anomaly_event_type")
    op.execute("ALTER TYPE anomaly_event_type_new RENAME TO anomaly_event_type")


def downgrade() -> None:
    # rapid_questions 를 다시 enum 에 복원 (데이터는 복원 불가).
    op.execute(
        """
        CREATE TYPE anomaly_event_type_old AS ENUM (
            'login_brute_force',
            'rapid_questions',
            'concurrent_ip_login',
            'repeated_question',
            'recovery_abuse',
            'rapid_followup_questions'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE anomaly_events
        ALTER COLUMN type TYPE anomaly_event_type_old
        USING type::text::anomaly_event_type_old
        """
    )
    op.execute("DROP TYPE anomaly_event_type")
    op.execute("ALTER TYPE anomaly_event_type_old RENAME TO anomaly_event_type")

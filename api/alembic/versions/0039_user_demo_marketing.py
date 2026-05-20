"""성별·생년월일·마케팅 활용 동의 컬럼 추가.

마이페이지 회원정보(`/my/profile`)에서 선택 입력으로 수집한다.

추가 컬럼:
- gender                  : 'male' | 'female' | NULL (선택 입력, 남/여만)
- birthdate               : DATE (전체 생년월일, NULL 허용)
- marketing_consent_at    : 마지막 동의 시각. NULL = 미동의/철회.
- marketing_withdrawn_at  : 마지막 철회 시각 (이력 보존용, 다음 동의에도 유지).

마케팅 동의는 알림톡·SMS·이메일 통합 단일 토글이다. 본 프로젝트의
'이메일 0건' 정책에 따라 실제 발송 채널은 알림톡·SMS만 사용한다.

down_revision='0038_qa_log_audit_fields'.
"""

from alembic import op

revision = "0039_user_demo_marketing"
down_revision = "0038_qa_log_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(10)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate DATE")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS marketing_consent_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS marketing_withdrawn_at TIMESTAMPTZ"
    )
    # gender는 'male'|'female'만 허용 — 애플리케이션 검증 + DB 가드 이중화.
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_gender_check"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_gender_check "
        "CHECK (gender IS NULL OR gender IN ('male', 'female'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_gender_check")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS marketing_withdrawn_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS marketing_consent_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS birthdate")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS gender")

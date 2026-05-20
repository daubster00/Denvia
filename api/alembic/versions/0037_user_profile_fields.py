"""회원정보 프로필 컬럼 추가 — 이름·우편번호·도로명/지번 주소·상세주소.

마이페이지 회원정보 수정(`/my/profile`) 도입에 따라 기존 `users`에 신규 필드를
추가한다. 모든 컬럼은 nullable로 시작 — 기존 가입자 데이터를 깨지 않게.

추가 컬럼:
- name           : 한국 이름 50자 여유. NULL 허용.
- postcode       : 다음 우편번호 API는 5자리 숫자. 미래 변경 여유로 String(10).
- address_road   : 도로명 또는 지번 주소(사용자가 우편번호 검색에서 선택).
- address_detail : 상세주소(동/호수 등 수동 입력).

down_revision='0036_popups_display_position'.
"""

from alembic import op

revision = "0037_user_profile_fields"
down_revision = "0036_popups_display_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(50)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS postcode VARCHAR(10)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS address_road VARCHAR(255)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS address_detail VARCHAR(100)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS address_detail")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS address_road")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS postcode")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS name")

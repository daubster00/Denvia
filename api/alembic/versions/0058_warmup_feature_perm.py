"""상단바 'AI 워밍업' 토글을 권한 매트릭스로 흡수.

배경:
- 기존 AdminWarmupToggle 은 마스터 등급만 볼 수 있게 컴포넌트 자체에서 분기.
- 운영자가 신뢰하는 sub_operator/커스텀 등급에도 임시 노출이 필요해지면
  코드 배포 없이 매트릭스에서 켤 수 있어야 한다.
- 매트릭스의 "page_route" 컬럼을 페이지 외에 '기능 노출 토글' 키로도 재사용한다.
  실제 라우팅 가드는 사용되지 않고, 라우터에서 require_admin_page() 호출 1곳에만 쓰인다.

변경:
1) admin_grade_page_permissions 에 (/admin/feature/openai-warmup, allowed=false) 행을
   현재 admin_grades 메타에 존재하는 모든 등급(master/pending 제외)에 대해 시드.
   - master  : 매트릭스 외 — 라우터 가드에서 항상 통과
   - pending : 매트릭스 외 — 가입 대기 단계라 시드 대상 아님
   - operator/sub_operator/커스텀 : allowed=false 로 시드 → 운영자가 매트릭스에서 직접 켜야 함

down_revision='0057_admin_grades_dynamic'.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0058_warmup_feature_perm"
down_revision = "0057_admin_grades_dynamic"
branch_labels = None
depends_on = None


_FEATURE_ROUTE = "/admin/feature/openai-warmup"
_EXCLUDED_GRADES = ("master", "pending")


def upgrade() -> None:
    bind = op.get_bind()

    grade_rows = bind.execute(
        sa.text("SELECT code FROM admin_grades WHERE code NOT IN ('master', 'pending')")
    ).fetchall()

    for (code,) in grade_rows:
        bind.execute(
            sa.text(
                "INSERT INTO admin_grade_page_permissions "
                "(admin_grade, page_route, allowed) "
                "VALUES (:g, :r, false) "
                "ON CONFLICT (admin_grade, page_route) DO NOTHING"
            ),
            {"g": code, "r": _FEATURE_ROUTE},
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM admin_grade_page_permissions WHERE page_route = :r"
        ).bindparams(r=_FEATURE_ROUTE)
    )

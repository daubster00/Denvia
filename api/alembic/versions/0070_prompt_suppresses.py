"""프롬프트 블록 상호배제(예외처리) 데이터화 — 게시판 #95.

기존에 코드에 하드코딩돼 있던 "특정 모듈 활성화 시 치식_위치·치면_방향 제외" 규칙을
prompt_module_configs.suppresses(JSONB list[block_id]) 컬럼으로 외부화한다.
관리자가 웹에서 블록별 '이 블록이 켜지면 숨길 블록'을 직접 편집할 수 있게 하는 백엔드 근거.

백필 = vendor build_prompt_template 하드코딩 규칙과 동일:
  브릿지 / 치주치료_산정 / 마취_산정 / 치주낭측정검사_횟수산정 → [치식_위치, 치면_방향]
그 외 블록은 NULL(= 배제 없음). 편집 전 라이브 동작은 완전히 동일하다.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0070_prompt_suppresses"
down_revision = "0069_prompt_modules_charge"
branch_labels = None
depends_on = None

_SUPPRESSORS = ["브릿지", "치주치료_산정", "마취_산정", "치주낭측정검사_횟수산정"]
_TARGETS = ["치식_위치", "치면_방향"]


def upgrade() -> None:
    op.add_column(
        "prompt_module_configs",
        sa.Column("suppresses", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    bind = op.get_bind()
    for bid in _SUPPRESSORS:
        bind.execute(
            sa.text(
                "UPDATE prompt_module_configs SET suppresses = CAST(:v AS JSONB) "
                "WHERE block_id = :bid"
            ),
            {"bid": bid, "v": json.dumps(_TARGETS, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.drop_column("prompt_module_configs", "suppresses")

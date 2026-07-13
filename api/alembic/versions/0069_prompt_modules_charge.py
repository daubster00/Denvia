"""게시판 #131 (2026-07-13): 신규 프롬프트 모듈 2개 seed.

- 즉처,충전 개념 / 치경부마모 2개를 prompt_module_configs 에 INSERT.
- content·trigger_config 를 하드카피하지 않고 vendor PROMPT_MODULES 에서 그대로 읽어
  파일값과 byte 단위 동치성을 보장한다(0068 과 동일 원칙).
- 런타임(build_prompt_with_overrides)은 파일 폴백으로 이미 반영되므로, 이 시드는
  #129 관리자 프롬프트 편집 화면에 2개 모듈을 노출/편집 가능하게 하는 용도다.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0069_prompt_modules_charge"
down_revision = "0068_prompt_trigger_config"
branch_labels = None
depends_on = None

_NEW = ["즉처,충전 개념", "치경부마모"]


def _trigger_config(block_id: str, module: dict) -> dict:
    """vendor 모듈 dict → trigger_config JSON. 매칭 4종 분기 (0068 과 동일)."""
    if block_id == "BASE":
        return {"mode": "base"}
    if "keywords_all" in module:
        return {"mode": "keywords_all", "keywords_all": list(module["keywords_all"])}
    if "keywords_combo" in module:
        combo = module["keywords_combo"]
        return {
            "mode": "keywords_combo",
            "set1": list(combo["set1"]),
            "independent": list(combo["independent"]),
        }
    if "group_keywords" in module and "required_keywords" in module:
        return {
            "mode": "group",
            "group_keywords": list(module["group_keywords"]),
            "required_keywords": list(module["required_keywords"]),
        }
    return {"mode": "keywords", "keywords": list(module["keywords"])}


def upgrade() -> None:
    from rag.prompt_builder import PROMPT_MODULES  # type: ignore[import-untyped]

    bind = op.get_bind()
    for bid in _NEW:
        module = PROMPT_MODULES[bid]
        tc = _trigger_config(bid, module)
        bind.execute(
            sa.text(
                "INSERT INTO prompt_module_configs (block_id, content, enabled, trigger_config) "
                "VALUES (:bid, :content, true, CAST(:tc AS JSONB)) "
                "ON CONFLICT (block_id) DO NOTHING"
            ),
            {
                "bid": bid,
                "content": module["text"],
                "tc": json.dumps(tc, ensure_ascii=False),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM prompt_module_configs WHERE block_id IN ('즉처,충전 개념','치경부마모')"
        )
    )

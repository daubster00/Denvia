"""#129: prompt_module_configs.trigger_config 추가 + 신규 5개 모듈 seed + block_id 폭 확장.

- 기존 5행(BASE·치식_위치·치면_방향·마취_산정·브릿지) content 는 절대 미변경(라이브 값 보존),
  trigger_config 만 vendor 파일 현재값에서 backfill.
- 신규 5행(치주치료_산정·치주낭측정검사_횟수산정·초진,재진·보험레진_와동분류·임플란트_치근면처치술)
  INSERT: content·trigger_config 를 vendor PROMPT_MODULES 에서 그대로 복사(동치성 보장).

content·trigger_config 를 하드카피하지 않고 vendor 를 import 해서 읽는다 —
한 글자라도 어긋나면 프롬프트 조립 동치성이 깨지므로, 원본을 직접 읽는 것이 가장 안전하다.
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0068_prompt_trigger_config"
down_revision = "0067_board_status_rework"
branch_labels = None
depends_on = None

_EXISTING = ["BASE", "치식_위치", "치면_방향", "마취_산정", "브릿지"]
_NEW = [
    "치주치료_산정",
    "치주낭측정검사_횟수산정",
    "초진,재진",
    "보험레진_와동분류",
    "임플란트_치근면처치술",
]


def _trigger_config(block_id: str, module: dict) -> dict:
    """vendor 모듈 dict → trigger_config JSON. 매칭 4종 분기."""
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
    # vendor 원본을 직접 읽어 content·trigger 를 확보(동치성 보장).
    from rag.prompt_builder import PROMPT_MODULES  # type: ignore[import-untyped]

    op.alter_column(
        "prompt_module_configs",
        "block_id",
        existing_type=sa.String(20),
        type_=sa.String(40),
        existing_nullable=False,
    )
    op.add_column(
        "prompt_module_configs",
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    bind = op.get_bind()

    # (a) 기존 5행: content 미변경, trigger_config 만 backfill.
    for bid in _EXISTING:
        module = PROMPT_MODULES.get(bid, {})
        tc = _trigger_config(bid, module)
        bind.execute(
            sa.text(
                "UPDATE prompt_module_configs SET trigger_config = CAST(:tc AS JSONB) "
                "WHERE block_id = :bid"
            ),
            {"bid": bid, "tc": json.dumps(tc, ensure_ascii=False)},
        )

    # (b) 신규 5행: content(파일 text) + trigger_config INSERT, enabled=true.
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
            "DELETE FROM prompt_module_configs WHERE block_id IN "
            "('치주치료_산정','치주낭측정검사_횟수산정','초진,재진','보험레진_와동분류','임플란트_치근면처치술')"
        )
    )
    op.drop_column("prompt_module_configs", "trigger_config")
    op.alter_column(
        "prompt_module_configs",
        "block_id",
        existing_type=sa.String(40),
        type_=sa.String(20),
        existing_nullable=False,
    )

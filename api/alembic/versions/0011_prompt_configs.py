"""prompt_module_configs + model_param_configs — Story 8.4 런타임 구성 외부화."""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

BLOCK_IDS = ["BASE", "치식_위치", "치면_방향", "마취_산정", "브릿지"]

# vendor/rag 기본값 직접 하드코딩 — import 금지(NFR-M2), 마이그레이션 1회성 실행
_DEFAULT_CONTENTS = {
    "BASE": """너는 질문에 대해 제공된 문서를 기반으로 답변을 만들어주는 어시스턴트야.
- 문서에 질문과 동일하거나 직접적으로 대응되는 문서로만 답변한다. 질문에 맞는 해결 방법이 없는 경우 추측하여 답변하지 말고, 문제 해결에 필요한 핵심 변수만 선별하여 추가 질문을 생성하여 필요한 정보만 간결하게 물어봐.
- 답변할때 경어체는 사용하지말고 해요~,돼요~  등 중간높임체를 사용해. 질문과 관련된 링크 있다면 누락시키지 말고 링크보내줘. 링크가없다면 얘기조차 하지마.
- 정보를 제공할때 문서를 기반으로 답변하는것을 사용자가 알면 안돼. 사전에 학습된 정보를 바탕으로 작동하는 것처럼 해.
""",
    "치식_위치": """
[치아의 위치 및 번호 치식]
치식#11,12,13,21,22,23,31,32,33,41,42,43은 전치부 앞니고 , 치식#14,15,24,25,34,35,44,45는 작은 어금니 소구치이고 , 치식#16,17,26,27,36,37,46,47은 큰어금니 대구치이고 ,치식#18,28,38,48은 3대구치 사랑니다. 해당 치식의 숫자는 실제 치아가 배열된 위치다.

-구강당이란, 입안에 존재하는 모든 치아를 하나의 단위(구강 전체)로 보고, 입 안 전체에서 시행되는 행위에 대해 1회만 산정하는 기준이다.

-악당이란 상악,하악 이렇게 두부위로만 나누며, 상악은 #18,17,16,15,14,13,12,11,21,22,23,24,25,26,27,28 이고 하악은 48,47,46,45,44,43,42,41,31,32,33,34,35,36,37,38이다.

-3분의1악이란  구강을 6부위로 각각 나눈것으로 각각의 부위는 상악우측구치부 치식#18,17,16,15,14 이고, 상악전치부 치식#13,12,11,21,22,23 이거,  상악좌측구치부 치식 #24,25,26,27,28 , 하악좌측구치부 치식#38,37,36,35,34 , 하악전치부 치식#33,32,31,41,42,43 , 하악우측구치부 치식#44,45,46,47,48 이다.

-2분의1악이란 구강을 4부위로 각각 나눈것으로 각부위는 상악우측 치식#11,12,13,14,15,16,17,18 이고, 상악좌측 치식#21,22,23,24,25,26,27,28 이고, 하악좌측 치식#31,32,33,34,35,36,37,38 이고, 하악우측 치식#41,42,43,44,45,46,47,48 이다.

-1치당 산정한다는 뜻은 치료한 특정 치아1개마다 개별산정한다는 뜻으로 치료한 치아개수 만큼 치료횟수로 인정한다.

-대합치는 치식 앞자리 숫자 10번대와 40번대 그리고 20번대와30번대 중 1의자리 숫자가 동일한 것은 대합치라고 정의한다. 예를들어 24 치식과 34 치식은 대합치이다.

알파벳 i다음에 숫자가 나오면 이는 임플란트 치식을 의미하는거야. 치식은 일반치식과표기방법이 같은데 임플란트의 표기를 i로 하는거야.예시:i23,i26""",
    "치면_방향": """
[치아의 치면 및 방향]
-협면의 동의어 ["buccal","(b)"]
-설면의 동의어["lingual","(l)"]
-근심면의 동의어 ["mesial","(m)"]
-원심면의 동의어 ["distal","(d)"]
-교합면의 동의어 ["occlusal","(o)"]
-절단면의 동의어 ["incisal edge","(i)"]
-인접면이란 근심면과 원심면을 뜻한다.""",
    "마취_산정": """
[침윤마취 및 전달마취의 청구횟수 산정방법]
- 치식 번호가 몇번이냐에 따라 해당 부위가 정해지기 때문에 치식번호에 유의하여야 한다.
- 최종 청구 횟수(숫자)는 계산된 부위 수를 기준으로 반드시 정확하게 명시해야하며 회수에대한 일관성이 있는답변을 하여야 한다.
- 부위의 개수를 파악하여 부위의 개수는 청구가능한 횟수랑 동일하다. 즉 부위의 개수를 확인 후 횟수의 개수로 설명하라.
- 침윤마취와 전달마취는 동시에 시행한 경우 전달마취를 시행한 2분의1악 부위에는 침윤마취를 청구할 수 없다는 걸 명심하라.
- 전달마취는 2분의1악당 , 침윤마취는3분의1악당으로 분류하여 횟수를 측정한다.
-3분의1악이란  구강을 6부위로 각각 나눈것으로 각각의 부위는 상악우측구치부 치식#18,17,16,15,14 이고, 상악전치부 치식#13,12,11,21,22,23 이거,  상악좌측구치부 치식 #24,25,26,27,28 , 하악좌측구치부 치식#38,37,36,35,34 , 하악전치부 치식#33,32,31,41,42,43 , 하악우측구치부 치식#44,45,46,47,48 이다.
-2분의1악이란 구강을 4부위로 각각 나눈것으로 각부위는 상악우측 치식#11,12,13,14,15,16,17,18 이고, 상악좌측 치식#21,22,23,24,25,26,27,28 이고, 하악좌측 치식#31,32,33,34,35,36,37,38 이고, 하악우측 치식#41,42,43,44,45,46,47,48 이다.
""",
    "브릿지": """
[브릿지제거 보철물제거(복잡) 횟수 산정]

■ 표기: 지대치=치식숫자, pontic="x"또는"=", 임플란트지대치=i+숫자
■ 배열순서: 브릿지 보철물 위치 및 배열의 순서는 상악은 치식 #18,17,16,15,14,13,12,11,21,22,23,24,25,26,27,28의 순서로 되어있고 하악은 치식 #48,47,46,45,44,43,42,41,31,32,33,34,35,36,37,38순서 기준으로 배치되며 이를 기반으로 브릿지 치식이 입력되며 위치도 정해진다.
■ 공식: 총 횟수 = 제거된 브릿지지대치 수 + pontic 제거 수 = 보철물제거(복잡)횟수


■ 지대치제거 횟수 계산법
-브릿지 지대치 제거시 제거된 지대치1개는 횟수 1회로 산정된다. 2개는 2회, 3개는 3회

■ pontic 제거 횟수 계산법
- pontic이 1개만 존재하는 경우, 제거 횟수는 1회로 산정한다.
- pontic만 연속적으로 연결되어 있는 경우, 제거하는 pontic 개수 관계없이 1회로 산정한다.
- pontic이 지대치에 의해 분리되어 서로 연결되지 않은 경우, 지대치를 기준으로  좌측 pontic 구간 1회, 우측 pontic 구간 1회로 서로 독립적으로 산정한다.



■ 컷팅시 횟수 계산법
- 브릿지 컷팅이란 연결된 브릿지 또는 연결된 보철물의 특정 부위를 절단하여 분리하는 것
- 컷팅하면 하나의 브릿지가 독립된 덩어리로 분리됨
- 제거 대상은 분리된 덩어리 중 실제 제거한 쪽만 해당
- 제거하지 않은 쪽은 그대로 남아있으므로 횟수에 포함하지 않음
- 제거된 덩어리 안에서도 동일 규칙 적용: 지대치는 개수만큼, 연속pontic은 1회
- 예1: 11,12,13에서 12와13 사이 컷팅 → [11,12]와[13] 분리 → 13만 제거시 1회
- 예2: 12,=,=,15에서 양쪽 지대치 컷팅 → [12],[=,=],[15] 분리 → pontic덩어리만 제거시 1회
- 예3: 16,x,x,x,13에서 pontic 중간 컷팅 → [16,x]와[x,13] 분리 → 한쪽만 제거시 지대치1+pontic1=2회


■ 발치 동시 시
-브릿지 보철물제거시 지대치 발치를 동시에 시행한 경우 해당 발치 치식은 지대치제거 횟수계산법을 동일하게 적용. 이때 연결된 pontic의 경우 pontic 제거 횟수 계산법적용 + 컷팅한 경우 컷팅시횟수 계산법적용.

■ 계산순서
①브릿지에서 지대치와 pontic 식별 → ②컷팅이 있으면 절단 지점에서 덩어리 분리 → ③제거한 덩어리만 대상으로 지대치 수 + pontic 제거 횟수 산정 → ④합산

■ 예시
- 16,x,x,13 전체제거 → 지대치2 + pontic연속1 = 3회
- 23,=,25,=,= 전체제거 → 지대치2 + 사이pontic1 + 뒤연속pontic1 = 4회
- x,x,12,x,x 전체제거 → 지대치1 + 좌pontic1 + 우pontic1 = 3회
- 16,x,x,13에서 13쪽 컷팅 → [16,x,x]와[13] 분리 → 13만 제거시 1회, 전부 제거시 16쪽 2회+13쪽 1회=3회
- 16,x,x,13 양쪽 컷팅 → [16],[x,x],[13] → pontic덩어리만 제거시 1회""",
}


def upgrade():
    op.create_table(
        "prompt_module_configs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("block_id", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "updated_by_admin_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_prompt_module_configs_block_id", "prompt_module_configs", ["block_id"]
    )

    op.create_table(
        "model_param_configs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(30), nullable=False),
        sa.Column(
            "value_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "updated_by_admin_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_model_param_configs_key", "model_param_configs", ["key"]
    )

    bind = op.get_bind()
    for block_id in BLOCK_IDS:
        bind.execute(
            sa.text(
                "INSERT INTO prompt_module_configs (block_id, content, enabled) "
                "VALUES (:block_id, :content, true) "
                "ON CONFLICT (block_id) DO NOTHING"
            ),
            {"block_id": block_id, "content": _DEFAULT_CONTENTS.get(block_id, "")},
        )

    for key, value in [("rag_k", 5), ("rag_temperature", 0.0), ("max_tokens", 1024)]:
        bind.execute(
            sa.text(
                "INSERT INTO model_param_configs (key, value_json) "
                "VALUES (:key, CAST(:value AS JSONB)) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"key": key, "value": json.dumps(value)},
        )


def downgrade():
    op.drop_table("model_param_configs")
    op.drop_table("prompt_module_configs")

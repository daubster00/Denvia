"""#149 재검수 P1-1 — 저장 답변 재생의 **원자적 선점** 컬럼 2개.

배경(`docs/CODE_REVIEW_149_2026-11-03.md` §12):

``find_replayable``(전송 실패 답변 재생 후보 조회)이 평범한 SELECT 였고, 실제 전달 표시
(``delivered=true``)는 그 뒤 ``stream_saved`` 에서 따로 UPDATE 했다. 두 동작 사이에 틈이
있어서, 사용자가 같은 질문을 거의 동시에 두 번 보내면(또는 재시도 버튼을 연타하면)
두 요청이 **같은 행을 함께 재생**했다. 질문 횟수는 차감되지 않으니 재생이 공짜로
복제되고, 둘 중 하나가 delivered 를 먼저 세우면 다른 쪽은 이미 전달된 답변을 또 보낸다.

조치: "재생 권한" 을 DB 행에 명시적으로 선점(claim)한다.

- ``replay_claimed_at``: 재생 권한을 가져간 시각. 조건부 ``UPDATE ... RETURNING`` 으로
  NULL → now() 로 바꾸는 데 성공한 요청 **단 하나**만 재생한다.
- ``replay_claim_token``: 그 선점의 소유자 표식(uuid hex). 연결이 끊겨 선점을 풀 때,
  **자기 선점만** 풀도록 비교한다(다른 요청이 이미 리스 만료로 가져간 선점을 지우면
  그쪽 재생이 중복 허용 상태가 된다).

리스(lease): 연결이 끊겨 선점 해제가 못 돌아가도 행이 영구히 잠기면 안 된다.
``REPLAY_CLAIM_LEASE_SECONDS``(qa_service, 현재 30초)가 지난 선점은 만료로 보고 다시
가져갈 수 있다.

두 컬럼 모두 additive · nullable. 기존 행은 NULL = "선점 없음" 으로 읽혀 기존 재생
동작과 그대로 호환된다. 0075 는 이미 로컬·운영 적용 대상이라 손대지 않고 새로 만든다.
"""
import sqlalchemy as sa
from alembic import op

revision = "0076_qa_replay_claim"
down_revision = "0075_qa_history_trust"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_logs",
        sa.Column("replay_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "qa_logs",
        sa.Column("replay_claim_token", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("qa_logs", "replay_claim_token")
    op.drop_column("qa_logs", "replay_claimed_at")

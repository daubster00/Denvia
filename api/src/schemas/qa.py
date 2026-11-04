"""QA 관련 Pydantic 스키마."""

from typing import Literal

from pydantic import BaseModel, Field

from api.src.services.chat_history_service import MAX_HISTORY_TURN_IDS


class QAEchoRequest(BaseModel):
    question_text: str = Field(min_length=1, max_length=2000)


class QAEchoResponse(BaseModel):
    qa_log_id: int
    question_text: str
    rule_matched: bool
    answer_text: str


class QAStreamRequest(BaseModel):
    """질의응답 스트림 요청.

    **이전 대화 전달 방식 (2026-11-03 검수 P0-2 로 변경)**

    ~~과거 질문·답변 문자열을 브라우저가 보낸다.~~ 폐기. 조작된 과거 답변이 프롬프트에
    그대로 들어갔고(프롬프트 주입), 계정 전환 후에도 탭에 남았다.

    지금은 **서버가 발급한 ``qa_log_id`` 목록만** 받는다. 질문·답변 본문은 서버가 자기
    로그에서 다시 읽고, 소유권·정상완료·전달여부·응답종류를 모두 검사한다
    (``chat_history_service.load_verified_turns``). 검증을 통과하지 못한 id 는 조용히
    빠지므로, 최악의 경우에도 "맥락 없는 새 질문" 이 된다.

    개수 상한은 ``MAX_HISTORY_TURN_IDS``(30) 하나로 통일한다 — 프런트도 전송 직전에
    같은 값으로 자른다(검수 P0-6: 31개째부터 전부 422 로 거부되던 결함).
    """

    question_text: str = Field(min_length=1, max_length=2000)
    # 이전 대화 턴의 qa_log_id (오래된 것 → 최신 순). 생략하면 기존 단일 질문 동작.
    history_turn_ids: list[int] = Field(
        default_factory=list, max_length=MAX_HISTORY_TURN_IDS
    )
    # 사용자가 "다시 시도" 를 눌러 보낸 요청인가 (검수 P0-1).
    # 이전 대화가 딸린 질문은 이 값이 True 이고 맥락 지문까지 같을 때만 저장분을 재생한다.
    retry: bool = False


class FeedbackCreateRequest(BaseModel):
    qa_log_id: int = Field(ge=1)
    rating: Literal["good", "bad"]


class FeedbackResponse(BaseModel):
    qa_log_id: int
    rating: Literal["good", "bad"]
    change_count: int
    action: Literal["created", "updated", "unchanged"]

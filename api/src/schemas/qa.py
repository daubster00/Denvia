"""QA 관련 Pydantic 스키마."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class QAEchoRequest(BaseModel):
    question_text: str = Field(min_length=1, max_length=2000)


class QAEchoResponse(BaseModel):
    qa_log_id: int
    question_text: str
    rule_matched: bool
    answer_text: str


class QAStreamRequest(BaseModel):
    question_text: str = Field(min_length=1, max_length=2000)


class FeedbackCreateRequest(BaseModel):
    qa_log_id: int = Field(ge=1)
    rating: Literal["good", "bad"]


class FeedbackResponse(BaseModel):
    qa_log_id: int
    rating: Literal["good", "bad"]
    change_count: int
    action: Literal["created", "updated", "unchanged"]


# Story 2.6: Reframe payload schema (SSE event + structuring LLM 출력 schema 겸용).
ReframeOption = Annotated[str, Field(min_length=1, max_length=120)]


class ReframePayload(BaseModel):
    """역질문 응답 구조 — Story 2.6.

    follow_up_question: RAG 자유 텍스트 후속 질문을 한 문장으로 정규화 (개행→단일 공백).
    options: 3~4개 짧은 한국어 후속 답변 후보 (각 1~120자, trim, 개행 금지).
    """

    follow_up_question: str = Field(min_length=1, max_length=500)
    options: list[ReframeOption] = Field(min_length=3, max_length=4)

    @field_validator("follow_up_question", mode="before")
    @classmethod
    def _normalize_question(cls, v):
        if not isinstance(v, str):
            raise TypeError("follow_up_question must be a string")
        normalized = " ".join(v.split())
        if not normalized:
            raise ValueError("follow_up_question must not be blank")
        return normalized

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, v):
        if not isinstance(v, list):
            raise TypeError("options must be a list")
        normalized: list[str] = []
        for opt in v:
            if not isinstance(opt, str):
                raise TypeError("each option must be a string")
            if "\n" in opt or "\r" in opt:
                raise ValueError("options must not contain line breaks")
            stripped = opt.strip()
            if not stripped:
                raise ValueError("options must not be blank after trim")
            normalized.append(stripped)
        return normalized

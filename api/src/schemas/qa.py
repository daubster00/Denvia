"""QA 관련 Pydantic 스키마."""

from typing import Literal

from pydantic import BaseModel, Field


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

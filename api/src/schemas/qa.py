"""QA 관련 Pydantic 스키마."""

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

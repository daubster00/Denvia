"""고객문의 Pydantic 스키마 — Story 4.5 (F-504)."""

from pydantic import BaseModel, Field


class InquirySubmitRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class InquirySubmitResponse(BaseModel):
    inquiry_id: int

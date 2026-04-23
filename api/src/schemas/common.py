"""공용 API 응답 스키마 — Denvia 표준 에러 포맷."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """표준 에러 응답 — flat, 래퍼 없음 (architecture.md §416, §703)."""

    code: str
    message: str
    trace_id: str
    details: dict | None = None

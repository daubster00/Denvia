"""클라이언트 이벤트 로그 스키마 — Story 2.5."""

from pydantic import BaseModel


class ClientEventRequest(BaseModel):
    event: str
    trace_id: str | None = None  # 클라이언트 제공 선택적 상관 ID

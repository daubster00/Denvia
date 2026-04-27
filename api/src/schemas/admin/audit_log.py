"""감사 로그 Pydantic I/O 스키마 — Story 5.1."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    actor_user_id: int
    action: str
    target_type: str | None
    target_id: int | None
    ip: str | None
    ua: str | None
    trace_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    page: int
    per_page: int
    total: int

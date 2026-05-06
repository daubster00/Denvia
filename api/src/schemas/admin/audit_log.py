"""감사 로그 Pydantic I/O 스키마 — Story 5.1 + Story 6.2 확장.

Story 6.2 편차 3·5: AuditLogItem에 actor_email/target_email/diff_json 3 필드 추가
(기존 5.1 호출자 영향 0건 — 추가 필드는 모두 Optional, superset).
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    actor_user_id: int
    actor_email: str | None = None  # Story 6.2 신규 — users JOIN으로 채움 (편의성)
    action: str
    target_type: str | None = None
    target_id: int | None = None
    target_email: str | None = None  # Story 6.2 신규 — target_type='user'일 때만
    diff_json: dict[str, Any] | None = None  # Story 6.2 신규 — JSONB 그대로 dict 변환
    ip: str | None = None
    ua: str | None = None
    trace_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    page: int
    per_page: int
    total: int

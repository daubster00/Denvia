"""Story 10.4 — 관리자 활동 로그 페이지(`/admin/admins/logs`) Pydantic I/O.

기존 `audit_log.py`는 Story 5.1·6.2의 일반 감사 로그 라우터(`/admin/audit-logs`) 전용이고,
본 모듈은 `/admin/accounts/logs` 페이지 전용 신규 응답 형태(`actor_email`·`target_preview`·
`has_diff`·`next_cursor`)를 담는다. SSOT 분리 — 두 응답을 겹치지 않게 둔다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AdminLogListItem(BaseModel):
    id: int
    created_at: str  # ISO 8601 UTC string — 프론트가 KST 변환 (Story 5.5 패턴 일관)
    actor_user_id: int
    actor_email: str
    action: str
    target_type: str | None
    target_id: int | None
    target_preview: str | None
    ip: str | None
    has_diff: bool


class AdminLogListResponse(BaseModel):
    items: list[AdminLogListItem]
    next_cursor: str | None


class AdminLogDiffResponse(BaseModel):
    id: int
    diff_json: dict[str, Any] | list[Any] | None

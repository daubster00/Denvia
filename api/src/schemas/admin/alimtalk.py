"""Story 4.6 — 관리자 알림톡 관리 페이지 Pydantic 스키마.

엔드포인트 그룹 `/api/v1/admin/alimtalk/*` 의 응답 모델을 모두 본 모듈에서 정의한다.

응답 PII 정책 (NFR-S2):
- 평문 phone 은 응답·로그·UI 어디에도 노출하지 않는다.
- `phone_masked` 필드만 노출 — 마스킹 형식 "010-****-1234" (또는 비-010 시 "****XXXX").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── 공통 ────────────────────────────────────────────────────────────────


TemplateCategoryLiteral = Literal[
    "billing", "subscription", "notice", "system", "support", "sms"
]
ChannelLiteral = Literal["alimtalk", "sms"]
RecipientKindLiteral = Literal["user", "admin"]


# ── GET /admin/alimtalk/summary (AC-2) ──────────────────────────────────


class AlimtalkTemplateStat(BaseModel):
    """템플릿 1행의 통계 + 메타.

    `channel`: alimtalk(카카오) / sms — 관리자 UI 구분 칩에 사용.
    `aligo_tpl_code`: 알리고 콘솔 등록 코드(UH_/UI_). SMS·미등록은 None.
    `recipient_kind`: 발송 대상(user=일반 사용자, admin=운영 관리자).
    `trigger_situation`: 발송 시점·상황 설명 (상세보기에서 노출).
    `body_example`: 변수 채워진 발송 본문 예시 (상세보기에서 노출).
    """

    model_config = ConfigDict(extra="forbid")

    template_code: str
    title: str
    category: TemplateCategoryLiteral
    channel: ChannelLiteral
    aligo_tpl_code: str | None
    recipient_kind: RecipientKindLiteral
    trigger_situation: str
    body_example: str
    today_sent: int
    today_failed: int
    month_sent: int
    month_failed: int


class AlimtalkSummaryTotals(BaseModel):
    """전체 합계."""

    model_config = ConfigDict(extra="forbid")

    today_sent: int
    today_failed: int
    month_sent: int
    month_failed: int


class AlimtalkSummaryResponse(BaseModel):
    """요약 + 템플릿 카탈로그 응답."""

    model_config = ConfigDict(extra="forbid")

    totals: AlimtalkSummaryTotals
    templates: list[AlimtalkTemplateStat]


# ── GET /admin/alimtalk/logs (AC-3) ─────────────────────────────────────


class AlimtalkLogItem(BaseModel):
    """발송 로그 1건.

    `is_test`: 관리자 페이지에서 "테스트 발송" 버튼으로 보낸 row인지 여부.
               idempotency_key 가 `test:` 로 시작하는 row가 True.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: str
    sent_at: str | None
    user_id: int | None
    phone_masked: str | None
    channel: str
    status: str
    attempts: int
    last_error: str | None
    is_test: bool


class AlimtalkLogListResponse(BaseModel):
    """발송 로그 페이지네이션 응답.

    - page-number 모드: items + total/page/per_page/total_pages 채움. next_cursor=None.
    - cursor 모드(레거시): items + next_cursor 채움. total/page/per_page/total_pages=None.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[AlimtalkLogItem]
    next_cursor: str | None
    total: int | None = None
    page: int | None = None
    per_page: int | None = None
    total_pages: int | None = None


# ── GET/PUT/DELETE /admin/alimtalk/test-recipient (AC-6) ────────────────


class TestRecipientResponse(BaseModel):
    """수신 번호 마스킹 응답."""

    model_config = ConfigDict(extra="forbid")

    phone_masked: str | None
    is_set: bool


class TestRecipientUpdateRequest(BaseModel):
    """PUT body. 하이픈은 서비스에서 자동 strip."""

    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=10, max_length=20)


# ── POST /admin/alimtalk/test-send (AC-4) ───────────────────────────────


class TestSendRequest(BaseModel):
    """POST body — recipient_phone 은 body 미포함(서버 Redis 직독)."""

    model_config = ConfigDict(extra="forbid")

    template_code: str = Field(min_length=1, max_length=120)

    @field_validator("template_code")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class TestSendResponse(BaseModel):
    """발송 결과 — 성공·실패 둘 다 HTTP 200."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    template_code: str
    phone_masked: str | None
    aligo_response_code: str
    error_message: str | None
    message_id: str | None = None

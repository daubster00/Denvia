"""서비스 전체 런타임 설정 스키마 — Story 7.3/7.4 부분.

컨텐츠 관리 페이지에서 어드민이 직접 편집하는 4개 토글:
- show_subscribe_button: 구독 버튼 전역 노출 토글 (A-303)
- free_daily_quota: 무료 사용자 1일 질문 한도 (FR23)
- free_delay_enabled: 답변 의도적 지연 ON/OFF (A-305)
- free_delay_seconds: 무료 지연 초 (Story 6.3 정수 호환)
"""

from pydantic import BaseModel, Field


class RuntimeConfigResponse(BaseModel):
    show_subscribe_button: bool
    free_daily_quota: int
    free_delay_enabled: bool
    free_delay_seconds: int


class RuntimeConfigUpdateRequest(BaseModel):
    show_subscribe_button: bool
    free_daily_quota: int = Field(ge=0, le=9999)
    free_delay_enabled: bool
    free_delay_seconds: int = Field(ge=0, le=30)

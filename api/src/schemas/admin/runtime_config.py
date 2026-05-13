"""서비스 전체 런타임 설정 스키마 — Story 7.3/7.4 부분.

컨텐츠 관리 페이지에서 어드민이 직접 편집하는 4개 토글:
- show_subscribe_button: 구독 버튼 전역 노출 토글 (A-303)
- free_daily_quota: 무료 사용자 1일 질문 한도 (FR23)
- free_delay_enabled: 답변 의도적 지연 ON/OFF (A-305)
- free_delay_seconds: 무료 지연 초 (Story 6.3 정수 호환)

추가:
- ChatModelConfig*: 관리자 설정 페이지에서 RAG 본 체인 채팅 모델 선택.
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


class ChatModelConfigResponse(BaseModel):
    """현재 선택된 채팅 모델 + 허용 모델 목록(드롭다운 옵션 제공)."""

    chat_model: str
    allowed_models: list[str]
    default_model: str


class ChatModelConfigUpdateRequest(BaseModel):
    chat_model: str = Field(min_length=1, max_length=64)

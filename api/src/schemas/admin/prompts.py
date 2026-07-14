"""프롬프트·모델 파라미터 Pydantic I/O 스키마 — Story 8.4 / #129."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TriggerConfig(BaseModel):
    """모듈 발동조건(트리거 키워드). mode 별로 사용하는 리스트가 다르다.

    - base            : 트리거 없음(BASE 전용, 항상 포함)
    - keywords        : keywords 중 하나라도 매칭(OR)
    - keywords_all    : keywords_all 전부 매칭(AND)
    - keywords_combo  : set1 2개 이상 OR (set1 1개 + independent 1개)
    - group           : group_keywords 중 1개 + required_keywords 중 1개
    """

    mode: Literal["base", "keywords", "keywords_all", "keywords_combo", "group"]
    keywords: list[str] | None = None
    keywords_all: list[str] | None = None
    set1: list[str] | None = None
    independent: list[str] | None = None
    group_keywords: list[str] | None = None
    required_keywords: list[str] | None = None


class PromptBlockResponse(BaseModel):
    block_id: str
    # trigger_keywords: 발동조건을 평탄화한 목록(구버전 프론트 호환). 신규 프론트는 trigger_config 사용.
    trigger_keywords: list[str]
    trigger_config: TriggerConfig | None = None
    content: str
    enabled: bool
    updated_at: datetime
    # 상호배제(예외처리) — 이 블록이 켜지면 함께 숨길 블록 id 목록(#95).
    suppresses: list[str] | None = None
    # 원본(빌트인) 블록은 끄기만, 관리자 생성 블록만 완전 삭제 가능(프론트 삭제 버튼 노출 판단).
    deletable: bool = False

    model_config = {"from_attributes": True}


class PromptsListResponse(BaseModel):
    blocks: list[PromptBlockResponse]


class PromptUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    enabled: bool = True
    # 발동조건 편집. 생략(None) 시 기존 trigger_config 유지(글 내용만 변경하는 구버전 호환).
    trigger_config: TriggerConfig | None = None
    # 상호배제(예외처리) 편집. 생략(None) 시 기존 suppresses 유지. []는 "배제 없음"으로 명시 설정.
    suppresses: list[str] | None = None


class PromptCreateRequest(BaseModel):
    """관리자 신규 블록 생성. block_id = 블록 이름(고유). 발동조건 필수(vendor 폴백 없음)."""

    block_id: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1)
    enabled: bool = True
    trigger_config: TriggerConfig | None = None
    # 상호배제(예외처리) — 이 블록이 켜지면 함께 숨길 블록 id 목록. 생략 시 배제 없음.
    suppresses: list[str] | None = None


class PromptUpdateResponse(BaseModel):
    block_id: str
    content: str
    enabled: bool
    trigger_config: TriggerConfig | None = None
    suppresses: list[str] | None = None
    updated_at: datetime


class ModelParamsResponse(BaseModel):
    rag_k: int
    rag_temperature: float
    max_tokens: int
    # 사용자 질문 입력 글자수 상한 (시스템 프롬프트 제외, 순수 질문만). 기본 2000.
    max_question_chars: int = 2000


class ModelParamsUpdateRequest(BaseModel):
    # 범위 오류는 서비스 레이어에서 MODEL_PARAM_OUT_OF_RANGE 코드로 통일한다.
    rag_k: int
    rag_temperature: float
    max_tokens: int
    # 사용자 질문 입력 글자수 상한 (시스템 프롬프트 제외, 순수 질문만). 기본 2000.
    # 프론트 ModelParamForm 는 항상 전송 — 기본값은 구버전 클라이언트 안전망.
    max_question_chars: int = 2000

    @field_validator("rag_temperature")
    @classmethod
    def snap_to_step(cls, v: float) -> float:
        """0.05 단위로 스냅 (0.05 배수에서 0.005 이내면 반올림)."""
        return round(round(v / 0.05) * 0.05, 10)

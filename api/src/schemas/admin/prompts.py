"""프롬프트·모델 파라미터 Pydantic I/O 스키마 — Story 8.4."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PromptBlockResponse(BaseModel):
    block_id: str
    trigger_keywords: list[str]
    content: str
    enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptsListResponse(BaseModel):
    blocks: list[PromptBlockResponse]


class PromptUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    enabled: bool = True


class PromptUpdateResponse(BaseModel):
    block_id: str
    content: str
    enabled: bool
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

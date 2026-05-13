"""동의어 사전 admin Pydantic 스키마 — Story 8.5."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

MAX_CANONICAL_LEN = 100
MAX_SYNONYM_LEN = 100
MAX_SYNONYMS_PER_GROUP = 50


def _clean_term(value: str, *, field: str) -> str:
    """trim 후 길이/문자 검증. 빈 문자열은 ValueError."""
    if value is None:
        raise ValueError(f"{field} is required")
    v = str(value).strip()
    if not v:
        raise ValueError(f"{field} must not be empty")
    if len(v) > MAX_CANONICAL_LEN:
        raise ValueError(f"{field} too long (max {MAX_CANONICAL_LEN})")
    return v


def _clean_synonyms(values: list[str], *, canonical: str | None) -> list[str]:
    """trim + 빈/길이 검증 + 자기참조 제거 + 중복 제거(순서 보존). 최대 개수 검증."""
    if values is None:
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        v = str(raw).strip()
        if not v:
            continue
        if len(v) > MAX_SYNONYM_LEN:
            raise ValueError(f"synonym too long (max {MAX_SYNONYM_LEN}): {v[:20]}...")
        if canonical is not None and v == canonical:
            continue  # 자기참조 제거
        if v in seen:
            continue
        seen.add(v)
        cleaned.append(v)
    if len(cleaned) > MAX_SYNONYMS_PER_GROUP:
        raise ValueError(f"too many synonyms (max {MAX_SYNONYMS_PER_GROUP})")
    return cleaned


class SynonymGroupRead(BaseModel):
    id: int
    canonical_term: str
    synonyms: list[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class SynonymListResponse(BaseModel):
    groups: list[SynonymGroupRead]
    total: int
    page: int
    size: int


class SynonymGroupCreateRequest(BaseModel):
    canonical_term: str = Field(min_length=1, max_length=MAX_CANONICAL_LEN)
    synonyms: list[str] = Field(default_factory=list)

    @field_validator("canonical_term")
    @classmethod
    def _v_canonical(cls, v: str) -> str:
        return _clean_term(v, field="canonical_term")

    @field_validator("synonyms")
    @classmethod
    def _v_synonyms(cls, v: list[str], info) -> list[str]:
        canonical = info.data.get("canonical_term")
        return _clean_synonyms(v, canonical=canonical)


class SynonymGroupUpdateRequest(SynonymGroupCreateRequest):
    """대표어/동의어 동시 갱신. Create와 동일 검증."""


class ImportConflict(BaseModel):
    row: int
    canonical_term: str
    reason: str


class ImportInvalidRow(BaseModel):
    row: int
    error: str


class ImportSummary(BaseModel):
    to_create: int
    to_update: int
    conflicts: int
    invalid: int
    unchanged: int = 0


class ImportPreviewResponse(BaseModel):
    summary: ImportSummary
    conflicts: list[ImportConflict] = Field(default_factory=list)
    invalid: list[ImportInvalidRow] = Field(default_factory=list)

"""Story 10.5 — 등급 × 페이지 접근 권한 매트릭스 Pydantic 스키마.

GET /api/v1/admin/grade-permissions          → MatrixResponse
PATCH /api/v1/admin/grade-permissions        → UpdateRequest → MatrixRowResponse
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GradeConfigurable = Literal["operator", "sub_operator"]


class GradePermissionRow(BaseModel):
    """매트릭스 한 칸 — (등급, 페이지) 쌍."""
    model_config = ConfigDict(from_attributes=True)

    admin_grade: GradeConfigurable
    page_route: str
    allowed: bool


class PageMeta(BaseModel):
    """프론트에서 라벨/순서를 표시하기 위한 페이지 메타."""
    page_route: str
    label: str


class MatrixResponse(BaseModel):
    """매트릭스 전체. rows 는 (grade, route) 별 한 칸."""
    pages: list[PageMeta]
    grades: list[GradeConfigurable]
    rows: list[GradePermissionRow]


class UpdateRequest(BaseModel):
    admin_grade: GradeConfigurable
    page_route: str = Field(min_length=1, max_length=64)
    allowed: bool

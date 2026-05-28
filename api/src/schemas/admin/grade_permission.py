"""Story 10.5 — 등급 × 페이지 접근 권한 매트릭스 Pydantic 스키마.

GET /api/v1/admin/grade-permissions          → MatrixResponse
PATCH /api/v1/admin/grade-permissions        → UpdateRequest → GradePermissionRow

0057 이후 admin_grade 는 동적 코드(VARCHAR). 매트릭스의 grade_meta 에 라벨이 동봉된다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GradePermissionRow(BaseModel):
    """매트릭스 한 칸 — (등급, 페이지) 쌍."""
    model_config = ConfigDict(from_attributes=True)

    admin_grade: str
    page_route: str
    allowed: bool


class PageMeta(BaseModel):
    """프론트에서 라벨/순서를 표시하기 위한 페이지 메타."""
    page_route: str
    label: str


class GradeMeta(BaseModel):
    """매트릭스 컬럼 — 등급 코드 + 라벨."""
    code: str
    label: str
    is_builtin: bool


class MatrixResponse(BaseModel):
    """매트릭스 전체. rows 는 (grade, route) 별 한 칸."""
    pages: list[PageMeta]
    grades: list[str]
    grade_meta: list[GradeMeta]
    rows: list[GradePermissionRow]


class UpdateRequest(BaseModel):
    admin_grade: str = Field(min_length=1, max_length=32)
    page_route: str = Field(min_length=1, max_length=64)
    allowed: bool

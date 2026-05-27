"""관리자 계정 RBAC Pydantic 스키마 — Story 10.1 기반.

Epic 10 / ADR-0001 편차 #6 (2026-05-26 클라이언트 확정).
4등급 체계:
- master       : 마스터(시스템상 단일 — partial UNIQUE로 강제). 모든 관리자 페이지 + 운영 관리자 관리 가능.
- operator     : 운영 관리자. admin_grade_page_permissions 매트릭스의 (operator, route)=true 인 페이지 접근 (기본 전체 ON).
- sub_operator : 부운영자. admin_grade_page_permissions 매트릭스의 (sub_operator, route)=true 인 페이지 접근 (기본 전체 OFF).
- pending      : 가입 승인 대기. 모든 관리자 페이지 접근 불가(deps/auth.py에서 401 차단).

본 스토리(10.1)에서는 타입 정의 + Read/Create/Update 모델만 노출.
실제 CRUD 라우터는 Story 10.3에서 추가된다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# 4등급 ENUM과 1:1 매핑 — admin_grade_enum (마이그레이션 0054).
AdminGrade = Literal["master", "operator", "sub_operator", "pending"]


class AdminAccountRead(BaseModel):
    """관리자 계정 단건 조회 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    admin_grade: AdminGrade
    phone: str | None = None
    admin_blocked_until: datetime | None = None
    admin_block_reason: str | None = None
    admin_signup_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class AdminAccountCreate(BaseModel):
    """관리자 신규 생성 입력 — Story 10.2 가입 신청 또는 Story 10.3 직접 추가."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str = Field(min_length=10, max_length=20)
    admin_grade: AdminGrade = "pending"


class AdminAccountUpdate(BaseModel):
    """관리자 계정 수정 — 등급 변경·차단/해제 등 부분 갱신."""

    admin_grade: AdminGrade | None = None
    admin_blocked_until: datetime | None = None
    admin_block_reason: str | None = None

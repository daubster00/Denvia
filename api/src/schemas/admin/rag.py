"""RAG 관리 Pydantic I/O 스키마 — Story 8.1/8.2."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HierarchyPreviewItem(BaseModel):
    major: str
    minors: list[str]


class KnowledgeUploadResponse(BaseModel):
    upload_id: int
    filename: str
    size_bytes: int
    chunk_count: int
    category_count: int
    hierarchy_preview: list[HierarchyPreviewItem]


class KnowledgeListItem(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    size_bytes: int
    chunk_count: int | None
    category_count: int | None
    status: str
    uploaded_by_admin_id: int

    model_config = {"from_attributes": True}


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeListItem]
    page: int
    per_page: int
    total: int


class KnowledgeDetailResponse(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    last_modified_at: datetime
    size_bytes: int
    chunk_count: Optional[int]
    category_count: Optional[int]
    status: str
    content: str

    model_config = {"from_attributes": True}


class KnowledgeEditRequest(BaseModel):
    content: str


class KnowledgeEditResponse(BaseModel):
    id: int
    filename: str
    size_bytes: int
    chunk_count: int
    category_count: int
    status: str
    last_modified_at: datetime

    model_config = {"from_attributes": True}


class RebuildTriggerResponse(BaseModel):
    job_id: int
    target_slot: str


class RebuildJobStatusResponse(BaseModel):
    id: int
    status: str
    progress_percent: int
    stage: Optional[str]
    target_slot: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    swapped_at: Optional[datetime]
    chunk_count_after: Optional[int]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class ActiveRebuildInfo(BaseModel):
    job_id: int
    status: str
    progress_percent: int
    stage: Optional[str]


class RagStatusResponse(BaseModel):
    pending_changes_count: int
    last_rebuild_at: Optional[datetime] = None
    last_rebuild_status: Optional[str] = None
    active_rebuild: Optional[ActiveRebuildInfo] = None

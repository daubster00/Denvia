"""RebuildJob ORM 모델 — Story 8.3."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.src.models.base import Base

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)


class RebuildJob(Base):
    __tablename__ = "rebuild_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    triggered_by_admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    celery_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_QUEUED)
    progress_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_slot: Mapped[str] = mapped_column(String(1), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    swapped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ── 재구축 비용 (수정요청 게시판 #145) ───────────────────────
    # 재구축 1회에 실제로 임베딩된 토큰 수와 그 비용(USD).
    # tiktoken 으로 로컬 계산하므로 OpenAI 에 추가 호출이 나가지 않는다.
    # 2026-09-14 이전 재구축은 측정 자체가 없었으므로 NULL 로 남긴다(추측값 백필 금지).
    # cost_usd 정밀도는 qa_logs.cost_usd 와 맞춰 소수점 6자리.
    embedding_token_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    embedding_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default="NOW()")

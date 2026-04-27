"""qa_feedback 서비스 — Story 2.4 단일 upsert."""

from datetime import datetime, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.qa_feedback import QAFeedback
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.schemas.qa import FeedbackResponse

logger = structlog.get_logger(__name__)


async def upsert_feedback(
    *, db: AsyncSession, user: User, qa_log_id: int, rating: str
) -> FeedbackResponse:
    qa_log = (
        await db.execute(select(QALog).where(QALog.id == qa_log_id))
    ).scalar_one_or_none()
    if qa_log is None or qa_log.user_id != user.id:
        logger.warning(
            "qa.feedback.unauthorized",
            user_id=user.id,
            qa_log_id=qa_log_id,
            reason="not_found" if qa_log is None else "not_owner",
        )
        raise HTTPException(
            status_code=404,
            detail={"code": "QA_LOG_NOT_FOUND", "message": "해당 답변을 찾을 수 없습니다."},
        )

    return await _do_upsert(db=db, user=user, qa_log_id=qa_log_id, rating=rating)


async def _do_upsert(
    *, db: AsyncSession, user: User, qa_log_id: int, rating: str
) -> FeedbackResponse:
    existing = (
        await db.execute(
            select(QAFeedback).where(QAFeedback.qa_log_id == qa_log_id).with_for_update()
        )
    ).scalar_one_or_none()

    if existing is None:
        feedback = QAFeedback(qa_log_id=qa_log_id, rating=rating, change_count=0)
        db.add(feedback)
        try:
            await db.commit()
            await db.refresh(feedback)
        except IntegrityError:
            await db.rollback()
            return await _do_upsert(db=db, user=user, qa_log_id=qa_log_id, rating=rating)
        logger.info(
            "qa.feedback.created",
            user_id=user.id,
            qa_log_id=qa_log_id,
            rating=rating,
        )
        return FeedbackResponse(
            qa_log_id=qa_log_id,
            rating=rating,
            change_count=0,
            action="created",
        )

    if existing.rating == rating:
        logger.info(
            "qa.feedback.unchanged",
            user_id=user.id,
            qa_log_id=qa_log_id,
            rating=rating,
        )
        return FeedbackResponse(
            qa_log_id=qa_log_id,
            rating=existing.rating,
            change_count=existing.change_count,
            action="unchanged",
        )

    from_rating = existing.rating
    existing.rating = rating
    existing.change_count = existing.change_count + 1
    existing.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(existing)
    logger.info(
        "qa.feedback.updated",
        user_id=user.id,
        qa_log_id=qa_log_id,
        from_rating=from_rating,
        to_rating=rating,
        change_count=existing.change_count,
    )
    return FeedbackResponse(
        qa_log_id=qa_log_id,
        rating=existing.rating,
        change_count=existing.change_count,
        action="updated",
    )

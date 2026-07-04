"""#113 질의응답 검토 라우터.

prefix: /admin/qa-review  (main.py 에서 /api/v1 prefix 추가 → /api/v1/admin/qa-review/...)

운영진(sub_operator)이 사용자 질의응답을 검토해 굿/베드 + 코멘트를 남기고,
최고관리자(master/operator)가 검토완료 처리한다.
기존 qa_feedback(고객 피드백)과 완전히 분리된 별도 기능·테이블.

엔드포인트:
  GET    /admin/qa-review               목록 (require_admin_page)
  GET    /admin/qa-review/summary       통계 (master/operator)
  POST   /admin/qa-review/{id}/rate     굿/베드 + 평가 메모 (require_admin_page)
  PUT    /admin/qa-review/{id}/comment  평가 메모 (굿/베드 공통, require_admin_page)
  POST   /admin/qa-review/{id}/complete 검토완료 토글 (master/operator)
  POST   /admin/qa-review/bulk-delete   다중 삭제 (master/operator)
  GET    /admin/qa-review/export        xlsx (master/operator)
  GET    /admin/qa-review/settings      설정 조회 (master/operator)
  PUT    /admin/qa-review/settings      설정 변경 (master/operator)
"""

from __future__ import annotations

import io
from datetime import date

import structlog
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_grade, require_admin_page
from api.src.middleware.audit_actions import (
    AUDIT_QA_REVIEW_BULK_DELETE,
    AUDIT_QA_REVIEW_COMMENT,
    AUDIT_QA_REVIEW_COMPLETE,
    AUDIT_QA_REVIEW_RATE,
    AUDIT_QA_REVIEW_SETTINGS,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.qa_review import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    CommentRequest,
    CompleteRequest,
    EffectivePeriod,
    RateRequest,
    ReviewActionResponse,
    ReviewItem,
    ReviewListResponse,
    ReviewSeriesItem,
    ReviewSummary,
    ReviewSummaryResponse,
    ReviewUserInfo,
    SettingsResponse,
    SettingsUpdateRequest,
)
from api.src.services import qa_review_service
from api.src.services.finance_service import _excel_safe_cell

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/qa-review",
    tags=["admin-qa-review"],
    dependencies=[Depends(require_admin_page("/admin/qa-review"))],
)


PeriodParam = str  # today|3d|7d|month|custom (서비스에서 검증)


# ── 목록 ──────────────────────────────────────────────────────────────────────
@router.get("", response_model=ReviewListResponse)
async def list_reviews(
    response: Response,
    period: str = Query("7d", pattern="^(today|3d|7d|month|custom)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    rating: str = Query("all", pattern="^(all|good|bad|unrated)$"),
    review: str = Query("all", pattern="^(all|reviewed|unreviewed)$"),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ReviewListResponse:
    viewer_grade = getattr(actor, "admin_grade", None)
    settings = await qa_review_service.get_settings(db)
    max_lookback_days = settings["sub_operator_max_lookback_days"]

    data = await qa_review_service.list_reviews(
        db,
        viewer_grade=viewer_grade,
        period=period,  # type: ignore[arg-type]
        date_from=date_from,
        date_to=date_to,
        rating_filter=rating,  # type: ignore[arg-type]
        review_filter=review,  # type: ignore[arg-type]
        q=q,
        page=page,
        page_size=page_size,
        max_lookback_days=max_lookback_days,
    )

    # 작성자 정보 비노출은 기간 제한과 동일 기준(master/operator 가 아닌 모든 등급).
    hide_user = qa_review_service.is_period_restricted(viewer_grade)
    items: list[ReviewItem] = []
    for it in data["items"]:
        user_info = None if hide_user else ReviewUserInfo(**it["user"])
        items.append(
            ReviewItem(
                qa_log_id=it["qa_log_id"],
                question=it["question"],
                answer=it["answer"],
                created_at=it["created_at"],
                review=it["review"],
                user=user_info,
            )
        )

    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.qa_review.list.viewed",
        actor_user_id=actor.id,
        viewer_grade=viewer_grade,
        period=period,
        total=data["total"],
        page=page,
    )
    return ReviewListResponse(
        items=items,
        total=data["total"],
        page=page,
        page_size=page_size,
        viewer_grade=viewer_grade,
        effective_period=EffectivePeriod(**data["effective_period"]),
    )


# ── 통계 ──────────────────────────────────────────────────────────────────────
@router.get(
    "/summary",
    response_model=ReviewSummaryResponse,
    dependencies=[Depends(require_admin_grade("master", "operator"))],
)
async def review_summary(
    response: Response,
    period: str = Query("month", pattern="^(today|3d|7d|month|custom)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    bucket: str = Query("day", pattern="^(day|week|month)$"),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ReviewSummaryResponse:
    data = await qa_review_service.get_review_summary(
        db,
        period=period,  # type: ignore[arg-type]
        date_from=date_from,
        date_to=date_to,
        bucket=bucket,  # type: ignore[arg-type]
    )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.qa_review.summary.viewed",
        actor_user_id=actor.id,
        period=period,
        bucket=bucket,
    )
    return ReviewSummaryResponse(
        summary=ReviewSummary(**data["summary"]),
        series=[ReviewSeriesItem(**s) for s in data["series"]],
    )


# ── 굿/베드 ───────────────────────────────────────────────────────────────────
@router.post("/{qa_log_id}/rate", response_model=ReviewActionResponse)
@audit_action(AUDIT_QA_REVIEW_RATE)
async def rate(
    request: Request,
    qa_log_id: int,
    body: RateRequest,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ReviewActionResponse:
    state = await qa_review_service.upsert_rating(
        db,
        qa_log_id=qa_log_id,
        rating=body.rating,
        comment=body.comment,
        admin_id=actor.id,
    )
    await db.commit()
    logger.info(
        "admin.qa_review.rated",
        actor_user_id=actor.id,
        qa_log_id=qa_log_id,
        rating=state["rating"],
    )
    return ReviewActionResponse(qa_log_id=qa_log_id, **state)


# ── 평가 메모 (굿/베드 공통) ─────────────────────────────────────────────────
@router.put("/{qa_log_id}/comment", response_model=ReviewActionResponse)
@audit_action(AUDIT_QA_REVIEW_COMMENT)
async def update_comment(
    request: Request,
    qa_log_id: int,
    body: CommentRequest,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ReviewActionResponse:
    state = await qa_review_service.update_comment(
        db,
        qa_log_id=qa_log_id,
        comment=body.comment,
        admin_id=actor.id,
    )
    await db.commit()
    logger.info(
        "admin.qa_review.comment_updated",
        actor_user_id=actor.id,
        qa_log_id=qa_log_id,
    )
    return ReviewActionResponse(qa_log_id=qa_log_id, **state)


# ── 검토완료 토글 (master/operator) ──────────────────────────────────────────
@router.post(
    "/{qa_log_id}/complete",
    response_model=ReviewActionResponse,
    dependencies=[Depends(require_admin_grade("master", "operator"))],
)
@audit_action(AUDIT_QA_REVIEW_COMPLETE)
async def complete(
    request: Request,
    qa_log_id: int,
    body: CompleteRequest,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ReviewActionResponse:
    state = await qa_review_service.set_reviewed(
        db,
        qa_log_id=qa_log_id,
        reviewed=body.reviewed,
        admin_id=actor.id,
    )
    await db.commit()
    logger.info(
        "admin.qa_review.review_toggled",
        actor_user_id=actor.id,
        qa_log_id=qa_log_id,
        reviewed=body.reviewed,
    )
    return ReviewActionResponse(qa_log_id=qa_log_id, **state)


# ── 다중 삭제 (master/operator) ──────────────────────────────────────────────
@router.post(
    "/bulk-delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_admin_grade("master", "operator"))],
)
@audit_action(AUDIT_QA_REVIEW_BULK_DELETE)
async def bulk_delete(
    request: Request,
    body: BulkDeleteRequest,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BulkDeleteResponse:
    deleted = await qa_review_service.bulk_hide(
        db,
        qa_log_ids=body.qa_log_ids,
        admin_id=actor.id,
    )
    await db.commit()
    logger.info(
        "admin.qa_review.bulk_deleted",
        actor_user_id=actor.id,
        requested=len(body.qa_log_ids),
        deleted=deleted,
    )
    return BulkDeleteResponse(deleted=deleted)


# ── xlsx export (master/operator) ────────────────────────────────────────────
@router.get(
    "/export",
    dependencies=[Depends(require_admin_grade("master", "operator"))],
)
async def export(
    period: str = Query("month", pattern="^(today|3d|7d|month|custom)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    import openpyxl

    rows, truncated = await qa_review_service.get_export_rows(
        db, period=period, date_from=date_from, date_to=date_to  # type: ignore[arg-type]
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "질의응답검토"
    ws.append(
        [
            "생성일",
            "질문",
            "답변",
            "굿/베드",
            "코멘트",
            "평가자",
            "검토완료여부",
            "검토자",
        ]
    )
    for r in rows:
        ws.append(
            [
                _excel_safe_cell(r["created_at_kst"]),
                _excel_safe_cell(r["question"]),
                _excel_safe_cell(r["answer"]),
                _excel_safe_cell(r["rating_label"]),
                _excel_safe_cell(r["comment"]),
                _excel_safe_cell(r["rater"]),
                _excel_safe_cell(r["reviewed_label"]),
                _excel_safe_cell(r["reviewer"]),
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = "qa_review.xlsx"
    content_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    if truncated:
        headers["X-Truncated"] = "true"

    logger.info(
        "admin.qa_review.exported",
        actor_user_id=actor.id,
        row_count=len(rows),
        truncated=truncated,
    )
    return StreamingResponse(buf, media_type=content_type, headers=headers)


# ── 설정 (master/operator) ───────────────────────────────────────────────────
@router.get(
    "/settings",
    response_model=SettingsResponse,
    dependencies=[Depends(require_admin_grade("master", "operator"))],
)
async def get_settings(
    response: Response,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    settings = await qa_review_service.get_settings(db)
    await db.commit()  # 최초 조회 시 lazy 생성될 수 있어 커밋
    response.headers["Cache-Control"] = "no-store"
    return SettingsResponse(**settings)


@router.put(
    "/settings",
    response_model=SettingsResponse,
    dependencies=[Depends(require_admin_grade("master", "operator"))],
)
@audit_action(AUDIT_QA_REVIEW_SETTINGS)
async def update_settings(
    request: Request,
    body: SettingsUpdateRequest,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    settings = await qa_review_service.update_settings(
        db, days=body.sub_operator_max_lookback_days, admin_id=actor.id
    )
    await db.commit()
    logger.info(
        "admin.qa_review.settings_updated",
        actor_user_id=actor.id,
        sub_operator_max_lookback_days=settings["sub_operator_max_lookback_days"],
    )
    return SettingsResponse(**settings)

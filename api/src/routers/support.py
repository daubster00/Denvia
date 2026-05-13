"""고객문의 라우터 — Story 4.5 + 0030 게시판화.

POST   /api/v1/support/inquiries                  본문 + 타입 + 첨부 URL 배열로 제출. 분당 3회.
POST   /api/v1/support/inquiries/image-upload     multipart 이미지 1장 업로드. 분당 10회.
GET    /api/v1/support/inquiries                  본인 문의 목록(페이지네이션).
GET    /api/v1/support/inquiries/{inquiry_id}     본인 문의 상세 + 첨부 + 답변.
"""

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.deps.rate_limit import limit_inquiry
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.support import (
    InquiryDetailResponse,
    InquiryImageUploadResponse,
    InquiryListResponse,
    InquirySubmitRequest,
    InquirySubmitResponse,
)
from api.src.services import support_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/support", tags=["support"])

_ALLOWED_PER_PAGE = (10, 20, 50)


@router.post(
    "/inquiries",
    response_model=InquirySubmitResponse,
    status_code=201,
)
@limit_inquiry
async def submit_inquiry(
    request: Request,
    payload: InquirySubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> InquirySubmitResponse:
    """고객문의 제출 — INSERT 후 inquiry_id 반환.

    SLA: 본 엔드포인트는 알림톡을 보내지 않는다. 관리자 답변(Story 9.3) 시점에
    notification_service.send(template_code='support.reply_received') 호출.
    """
    inquiry_id = await support_service.submit_inquiry(
        db,
        user_id=current_user.id,
        inquiry_type=payload.inquiry_type,
        subject=payload.subject,
        body=payload.body,
        attachments=payload.attachments,
    )
    logger.info(
        "support.inquiry.submitted",
        user_id=current_user.id,
        inquiry_id=inquiry_id,
        inquiry_type=payload.inquiry_type,
        subject_length=len(payload.subject),
        body_length=len(payload.body),
        attachment_count=len(payload.attachments),
    )
    return InquirySubmitResponse(inquiry_id=inquiry_id)


@router.post(
    "/inquiries/image-upload",
    response_model=InquiryImageUploadResponse,
    status_code=201,
)
@limiter.limit("10/minute")
async def upload_inquiry_image(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> InquiryImageUploadResponse:
    """문의 이미지 multipart 업로드. 응답의 file_url을 submit 호출 시 attachments[].file_url 로 동봉."""
    result = await support_service.upload_inquiry_image(file)
    logger.info(
        "support.inquiry.image_uploaded",
        user_id=current_user.id,
        file_name=result.file_name,
        size_bytes=result.size_bytes,
        mime_type=result.mime_type,
    )
    return result


@router.get("/inquiries", response_model=InquiryListResponse)
async def list_my_inquiries(
    page: int = Query(1, ge=1),
    per_page: int = Query(20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> InquiryListResponse:
    """본인 1:1 문의 목록 — 최신순. has_attachments / reply_count 포함."""
    if per_page not in _ALLOWED_PER_PAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "per_page는 10/20/50 중 하나여야 합니다.",
            },
        )
    return await support_service.list_user_inquiries(
        db, user_id=current_user.id, page=page, per_page=per_page
    )


@router.get("/inquiries/{inquiry_id}", response_model=InquiryDetailResponse)
async def get_my_inquiry(
    inquiry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """본인 1:1 문의 상세 — 첨부 + 관리자 답변 포함. 타인 row 또는 미존재 시 404."""
    detail = await support_service.get_user_inquiry(
        db, user_id=current_user.id, inquiry_id=inquiry_id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "INQUIRY_NOT_FOUND",
                "message": "문의를 찾을 수 없습니다.",
            },
        )
    return detail

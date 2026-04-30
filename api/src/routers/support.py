"""고객문의 라우터 — Story 4.5 (F-504).

POST /api/v1/support/inquiries — 인증 사용자 한정. 분당 3회 레이트 리밋.
"""

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.deps.rate_limit import limit_inquiry
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.support import InquirySubmitRequest, InquirySubmitResponse
from api.src.services import support_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/support", tags=["support"])


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
        subject=payload.subject,
        body=payload.body,
    )
    logger.info(
        "support.inquiry.submitted",
        user_id=current_user.id,
        inquiry_id=inquiry_id,
        subject_length=len(payload.subject),
        body_length=len(payload.body),
    )
    return InquirySubmitResponse(inquiry_id=inquiry_id)

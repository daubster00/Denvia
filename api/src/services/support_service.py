"""고객문의 서비스 — Story 4.5 + 0030 게시판화.

- submit_inquiry(): 문의 INSERT + 첨부 검증·INSERT
- upload_inquiry_image(): multipart 이미지 검증·디스크 저장 (5MB / jpg·png·webp)
- list_user_inquiries(): 본인 목록 페이지네이션
- get_user_inquiry(): 본인 상세 + 첨부 + 관리자 답변

저장 경로: api/data/uploads/inquiries/<uuid>.<ext>
URL prefix: /static/inquiry-images
"""

from __future__ import annotations

import html as _html
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.customer_inquiry import CustomerInquiry
from api.src.models.inquiry_attachment import InquiryAttachment
from api.src.models.inquiry_reply import InquiryReply
from api.src.schemas.support import (
    InquiryAttachmentRef,
    InquiryAttachmentView,
    InquiryDetailResponse,
    InquiryImageUploadResponse,
    InquiryListItem,
    InquiryListResponse,
    InquiryReplyView,
    InquiryType,
    MAX_ATTACHMENTS_PER_INQUIRY,
)
from api.src.utils.html_sanitize import sanitize_body_html


# api/src/services/ → api/data/uploads/inquiries/
INQUIRY_IMAGE_DIR = (
    Path(__file__).parent.parent.parent / "data" / "uploads" / "inquiries"
)
INQUIRY_IMAGE_URL_PREFIX = "/static/inquiry-images"

_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _validate_attachment_url(file_url: str) -> None:
    """업로드된 file_url만 허용 — 외부 URL/path traversal 차단 (popup_service 패턴)."""
    if not file_url.startswith(INQUIRY_IMAGE_URL_PREFIX + "/"):
        raise HTTPException(
            422,
            detail={
                "code": "INQUIRY_ATTACHMENT_URL_INVALID",
                "message": "첨부는 업로드된 파일만 사용할 수 있습니다.",
            },
        )
    rel = file_url[len(INQUIRY_IMAGE_URL_PREFIX) + 1 :]
    if "/" in rel or ".." in rel:
        raise HTTPException(
            422,
            detail={
                "code": "INQUIRY_ATTACHMENT_URL_INVALID",
                "message": "잘못된 첨부 경로입니다.",
            },
        )


async def upload_inquiry_image(file: UploadFile) -> InquiryImageUploadResponse:
    """문의 이미지 multipart 업로드.

    검증 순서: MIME → 확장자 → 크기. 충돌·열거 차단을 위해 uuid prefix 사용.
    """
    if file.content_type not in _ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            422,
            detail={
                "code": "INQUIRY_IMAGE_MIME_INVALID",
                "message": "PNG·JPG·WEBP 이미지만 첨부할 수 있습니다.",
            },
        )

    raw_name = file.filename or ""
    ext = Path(raw_name).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            422,
            detail={
                "code": "INQUIRY_IMAGE_EXT_INVALID",
                "message": "PNG·JPG·WEBP 확장자만 허용됩니다.",
            },
        )

    contents = await file.read()
    size = len(contents)
    if size > _MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            422,
            detail={
                "code": "INQUIRY_IMAGE_TOO_LARGE",
                "message": "이미지 크기는 5MB 이하여야 합니다.",
            },
        )

    INQUIRY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    dest = INQUIRY_IMAGE_DIR / safe_filename
    dest.write_bytes(contents)

    return InquiryImageUploadResponse(
        file_url=f"{INQUIRY_IMAGE_URL_PREFIX}/{safe_filename}",
        file_name=raw_name[:255] or safe_filename,
        mime_type=file.content_type,
        size_bytes=size,
    )


async def submit_inquiry(
    db: AsyncSession,
    *,
    user_id: int,
    inquiry_type: InquiryType,
    subject: str,
    body: str,
    attachments: list[InquiryAttachmentRef],
) -> int:
    """문의 INSERT + 첨부 INSERT(있을 때만). 신규 inquiry_id 반환.

    body는 html.escape로 plain text 강제. attachments는 file_url prefix를 재검증한다.
    """
    if len(attachments) > MAX_ATTACHMENTS_PER_INQUIRY:
        raise HTTPException(
            422,
            detail={
                "code": "INQUIRY_TOO_MANY_ATTACHMENTS",
                "message": f"이미지는 최대 {MAX_ATTACHMENTS_PER_INQUIRY}장까지 첨부할 수 있습니다.",
            },
        )
    for att in attachments:
        _validate_attachment_url(att.file_url)

    safe_body = _html.escape(body)
    inquiry = CustomerInquiry(
        user_id=user_id,
        inquiry_type=inquiry_type,
        subject=subject,
        body=safe_body,
        status="open",
    )
    db.add(inquiry)
    await db.flush()  # id 확보

    for att in attachments:
        db.add(
            InquiryAttachment(
                inquiry_id=inquiry.id,
                file_url=att.file_url,
                file_name=att.file_name,
                mime_type=att.mime_type,
                size_bytes=att.size_bytes,
            )
        )

    await db.commit()
    await db.refresh(inquiry)
    return inquiry.id


async def list_user_inquiries(
    db: AsyncSession, *, user_id: int, page: int, per_page: int
) -> InquiryListResponse:
    """본인 문의 목록 — 최신순. has_attachments / reply_count 집계 포함."""
    total = (
        await db.execute(
            select(func.count(CustomerInquiry.id)).where(
                CustomerInquiry.user_id == user_id
            )
        )
    ).scalar_one()

    att_count_subq = (
        select(
            InquiryAttachment.inquiry_id.label("iid"),
            func.count(InquiryAttachment.id).label("att_count"),
        )
        .group_by(InquiryAttachment.inquiry_id)
        .subquery()
    )
    reply_count_subq = (
        select(
            InquiryReply.inquiry_id.label("iid"),
            func.count(InquiryReply.id).label("reply_count"),
        )
        .group_by(InquiryReply.inquiry_id)
        .subquery()
    )

    stmt = (
        select(
            CustomerInquiry.id,
            CustomerInquiry.inquiry_type,
            CustomerInquiry.subject,
            CustomerInquiry.status,
            CustomerInquiry.created_at,
            CustomerInquiry.resolved_at,
            func.coalesce(att_count_subq.c.att_count, 0).label("att_count"),
            func.coalesce(reply_count_subq.c.reply_count, 0).label("reply_count"),
        )
        .where(CustomerInquiry.user_id == user_id)
        .join(att_count_subq, att_count_subq.c.iid == CustomerInquiry.id, isouter=True)
        .join(
            reply_count_subq,
            reply_count_subq.c.iid == CustomerInquiry.id,
            isouter=True,
        )
        .order_by(CustomerInquiry.created_at.desc(), CustomerInquiry.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    rows = (await db.execute(stmt)).all()
    items = [
        InquiryListItem(
            id=r.id,
            inquiry_type=r.inquiry_type,
            subject=r.subject,
            status=r.status,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
            has_attachments=bool(int(r.att_count) > 0),
            reply_count=int(r.reply_count),
        )
        for r in rows
    ]
    return InquiryListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


async def get_user_inquiry(
    db: AsyncSession, *, user_id: int, inquiry_id: int
) -> InquiryDetailResponse | None:
    """본인 문의 상세 — 타인 row 또는 미존재 시 None."""
    inquiry = (
        await db.execute(
            select(CustomerInquiry).where(
                CustomerInquiry.id == inquiry_id,
                CustomerInquiry.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if inquiry is None:
        return None

    att_rows = (
        await db.execute(
            select(InquiryAttachment)
            .where(InquiryAttachment.inquiry_id == inquiry_id)
            .order_by(InquiryAttachment.id.asc())
        )
    ).scalars().all()

    reply_rows = (
        await db.execute(
            select(InquiryReply)
            .where(InquiryReply.inquiry_id == inquiry_id)
            .order_by(InquiryReply.created_at.asc(), InquiryReply.id.asc())
        )
    ).scalars().all()

    return InquiryDetailResponse(
        id=inquiry.id,
        inquiry_type=inquiry.inquiry_type,
        subject=inquiry.subject,
        body=inquiry.body,
        status=inquiry.status,
        created_at=inquiry.created_at,
        resolved_at=inquiry.resolved_at,
        attachments=[
            InquiryAttachmentView(
                id=a.id,
                file_url=a.file_url,
                file_name=a.file_name,
                mime_type=a.mime_type,
                size_bytes=a.size_bytes,
            )
            for a in att_rows
        ],
        replies=[
            InquiryReplyView(
                reply_id=r.id,
                reply_html_safe=sanitize_body_html(r.reply_html) or "",
                created_at=r.created_at,
            )
            for r in reply_rows
        ],
    )

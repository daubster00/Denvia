"""고객문의 서비스 — Story 4.5 (F-504).

submit_inquiry(): 사용자 문의 INSERT.
- subject: 200자 제한은 Pydantic 단계에서 강제 (max_length=200)
- body: 5000자 제한 + html.escape()로 plain text 강제 저장
- 알림톡 발송 0건 — 관리자 답변 시점(Story 9.3)에 SUPPORT_REPLY 템플릿 송출
"""

from __future__ import annotations

import html as _html

from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.customer_inquiry import CustomerInquiry


async def submit_inquiry(
    db: AsyncSession, user_id: int, subject: str, body: str
) -> int:
    """고객문의를 INSERT하고 신규 inquiry_id를 반환한다."""
    safe_body = _html.escape(body)
    inquiry = CustomerInquiry(
        user_id=user_id,
        subject=subject,
        body=safe_body,
        status="open",
    )
    db.add(inquiry)
    await db.commit()
    await db.refresh(inquiry)
    return inquiry.id

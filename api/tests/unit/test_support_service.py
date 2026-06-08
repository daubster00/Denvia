"""api/src/services/support_service 단위 테스트 — Story 4.5 (T4.5)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services import support_service


@pytest.mark.asyncio
async def test_submit_inquiry_escapes_html_in_body() -> None:
    """body 내 <script> 등은 html.escape() 적용 후 저장된다."""
    captured: dict = {}

    db = MagicMock()
    db.add = MagicMock(side_effect=lambda inq: captured.setdefault("inquiry", inq))
    db.commit = AsyncMock()

    async def _flush():
        inq = captured.get("inquiry")
        if inq is not None:
            inq.id = 88

    db.flush = AsyncMock(side_effect=_flush)
    db.refresh = AsyncMock()

    inquiry_id = await support_service.submit_inquiry(
        db,
        user_id=1,
        inquiry_type="billing",
        subject="결제 문의",
        body='<script>alert(1)</script>',
        attachments=[],
    )
    assert inquiry_id == 88
    inq = captured["inquiry"]
    assert inq.user_id == 1
    assert inq.subject == "결제 문의"
    # html.escape는 < → &lt;, > → &gt; 로 치환
    assert "&lt;script&gt;" in inq.body
    assert "<script>" not in inq.body
    assert inq.status == "open"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_inquiry_preserves_korean_text() -> None:
    """한글 본문은 escape에 의해 영향받지 않는다."""
    captured: dict = {}

    db = MagicMock()
    db.add = MagicMock(side_effect=lambda inq: captured.setdefault("inquiry", inq))
    db.commit = AsyncMock()

    async def _flush():
        inq = captured.get("inquiry")
        if inq is not None:
            inq.id = 1

    db.flush = AsyncMock(side_effect=_flush)
    db.refresh = AsyncMock()

    await support_service.submit_inquiry(
        db,
        user_id=42,
        inquiry_type="other",
        subject="문의",
        body="안녕하세요. 결제가 두 번 청구된 것 같아요.",
        attachments=[],
    )
    inq = captured["inquiry"]
    assert "안녕하세요" in inq.body
    assert "결제가 두 번 청구" in inq.body

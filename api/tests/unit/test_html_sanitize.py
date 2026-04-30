"""api/src/utils/html_sanitize 단위 테스트 — Story 4.5 AC-12."""

from api.src.utils.html_sanitize import sanitize_body_html


def test_strips_script_tags() -> None:
    raw = "<p>안녕</p><script>alert(1)</script>"
    out = sanitize_body_html(raw)
    assert "<script>" not in out
    assert "alert" not in out
    assert "<p>안녕</p>" in out


def test_strips_event_handlers() -> None:
    raw = '<a href="https://example.com" onclick="evil()">link</a>'
    out = sanitize_body_html(raw)
    assert "onclick" not in out
    assert "evil" not in out
    assert "https://example.com" in out


def test_blocks_javascript_urls() -> None:
    raw = '<a href="javascript:alert(1)">click</a>'
    out = sanitize_body_html(raw)
    # javascript: 스킴이 url_schemes에 없으므로 href가 제거됨
    assert "javascript:" not in out


def test_blocks_mailto_urls() -> None:
    """이메일 0건 정책 일관성 — mailto: 차단(memory project_email_zero_policy)."""
    raw = '<a href="mailto:contact@example.com">메일</a>'
    out = sanitize_body_html(raw)
    assert "mailto:" not in out


def test_preserves_allowed_tags_and_link_rel() -> None:
    raw = (
        "<p><strong>중요</strong></p>"
        "<ul><li>1</li><li>2</li></ul>"
        '<a href="https://denvia.kr" target="_blank">링크</a>'
        '<img src="https://denvia.kr/a.png" alt="설명">'
    )
    out = sanitize_body_html(raw)
    assert "<strong>중요</strong>" in out
    assert "<ul>" in out
    assert "<li>1</li>" in out
    assert "https://denvia.kr" in out
    assert "noopener" in out  # link_rel 자동 부착
    assert "noreferrer" in out
    assert 'alt="설명"' in out


def test_empty_input_returns_empty() -> None:
    assert sanitize_body_html("") == ""

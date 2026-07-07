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


def test_preserves_preset_hex_color() -> None:
    raw = '<span style="color: #dc2626">빨강</span>'
    out = sanitize_body_html(raw)
    assert 'style="color: #dc2626"' in out


def test_normalizes_rgb_preset_color_to_hex() -> None:
    """수정요청 #119 — Tiptap 재편집 시 브라우저가 hex를 rgb로 바꾸는 케이스.

    프리셋 색이면 rgb(R, G, B) 형식이어도 hex로 정규화해 통과시켜야 한다.
    """
    raw = '<span style="color: rgb(220, 38, 38)">빨강</span>'
    out = sanitize_body_html(raw)
    assert 'style="color: #dc2626"' in out
    assert "rgb" not in out  # 출력은 항상 소문자 hex


def test_normalizes_rgba_alpha_one_preset_color_to_hex() -> None:
    raw = '<span style="color: rgba(37, 99, 235, 1)">파랑</span>'
    out = sanitize_body_html(raw)
    assert 'style="color: #2563eb"' in out


def test_strips_rgb_non_preset_color() -> None:
    raw = '<span style="color: rgb(1, 2, 3)">임의색</span>'
    out = sanitize_body_html(raw)
    assert "style" not in out
    assert "임의색" in out


def test_strips_rgba_translucent_preset_color() -> None:
    """alpha != 1 이면 프리셋과 동치가 아니므로 제거."""
    raw = '<span style="color: rgba(220, 38, 38, 0.5)">반투명</span>'
    out = sanitize_body_html(raw)
    assert "style" not in out
    assert "반투명" in out


def test_rgb_color_with_font_size_keeps_both() -> None:
    raw = '<span style="color: rgb(22, 163, 74); font-size: 20px">본문</span>'
    out = sanitize_body_html(raw)
    assert "color: #16a34a" in out
    assert "font-size: 20px" in out

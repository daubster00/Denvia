"""HTML 본문 sanitize — Story 4.5.

nh3 (Rust ammonia 바인딩) 사용. <script>·on*·javascript: URL을 제거하고
허용 태그/속성만 남긴다.

mailto: 스킴은 의도적으로 제외 — 이메일 0건 정책(memory project_email_zero_policy)
일관성을 위해 본문 링크에서도 사용자 이메일 클라이언트 호출을 차단한다.

호출 지점:
- GET /me/inbox 응답 직전 (items[*].body_html → body_html_safe)
- GET /me/popups/active 응답 직전
- (Story 7.1/7.2 admin publish 시점 INSERT 전 이중 방어)
"""

import nh3

_ALLOWED_TAGS = frozenset({"p", "br", "b", "strong", "i", "em", "ul", "ol", "li", "a", "img"})
# 주의: "a" 태그의 "rel"은 link_rel="noopener noreferrer" 옵션이 자동 부착하므로
# attributes에 명시 금지(nh3 0.3+ 검증). target은 외부 링크 새 탭용.
_ALLOWED_ATTRS = {
    "a": {"href", "target"},
    "img": {"src", "alt"},
}
_ALLOWED_URL_SCHEMES = {"http", "https"}  # mailto/javascript/data: 제외


def sanitize_body_html(raw: str) -> str:
    """사용자 노출 직전 sanitize."""
    if not raw:
        return ""
    return nh3.clean(
        raw,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_ALLOWED_URL_SCHEMES,
        strip_comments=True,
        link_rel="noopener noreferrer",
    )


def safe_external_url(raw: str | None) -> str | None:
    """팝업 link_url 등 단일 URL 필드 방어용 — http/https만 통과시킨다.

    body_html은 nh3가 javascript:/data:/mailto: 등을 제거하지만 link_url처럼
    별도 컬럼은 sanitize 대상 밖이라 클릭형 XSS(`javascript:alert(1)`) 노출 위험이
    있다. 응답 직전 본 헬퍼로 한 번 더 거른다.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    # `javascript:`, `data:`, `vbscript:`는 콜론 기준으로 스킴이 식별되며
    # 공백·탭·개행이 prefix로 붙어 우회되는 케이스를 strip()으로 잘라낸다.
    lower = candidate.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return None
    return candidate

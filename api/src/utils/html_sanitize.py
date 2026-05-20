"""HTML 본문 sanitize — Story 4.5 + 7.2 v3.

nh3 (Rust ammonia 바인딩) 사용. <script>·on*·javascript: URL을 제거하고
허용 태그/속성만 남긴다.

mailto: 스킴은 의도적으로 제외 — 이메일 0건 정책(memory project_email_zero_policy)
일관성을 위해 본문 링크에서도 사용자 이메일 클라이언트 호출을 차단한다.

Story 7.2 v3 — <span style="color:...; font-size:...">를 허용한다.
Tiptap의 Color + FontSize 확장이 인라인 style을 그대로 쓰므로, 임의 CSS 주입을
막기 위해 attribute_filter로 8가지 프리셋 색상과 5가지 크기 px만 통과시킨다.

호출 지점:
- GET /me/inbox 응답 직전 (items[*].body_html → body_html_safe)
- GET /me/popups/active 응답 직전
- (Story 7.1/7.2 admin publish 시점 INSERT 전 이중 방어)
"""

import re

import nh3

_ALLOWED_TAGS = frozenset(
    {"p", "br", "b", "strong", "i", "em", "ul", "ol", "li", "a", "img", "span"}
)
# 주의: "a" 태그의 "rel"은 link_rel="noopener noreferrer" 옵션이 자동 부착하므로
# attributes에 명시 금지(nh3 0.3+ 검증). target은 외부 링크 새 탭용.
_ALLOWED_ATTRS = {
    "a": {"href", "target"},
    "img": {"src", "alt"},
    "span": {"style"},
}
_ALLOWED_URL_SCHEMES = {"http", "https"}  # mailto/javascript/data: 제외

# 팝업 본문에서 허용할 색 8종(소문자 hex). 프리셋 외 색은 모두 차단.
_ALLOWED_COLORS = frozenset(
    {
        "#18181b",  # 검정
        "#6b7280",  # 회색
        "#dc2626",  # 빨강
        "#ea580c",  # 주황
        "#ca8a04",  # 노랑
        "#16a34a",  # 초록
        "#2563eb",  # 파랑
        "#7c3aed",  # 보라
    }
)
_ALLOWED_FONT_SIZES_PX = frozenset({12, 14, 16, 20, 24})

_STYLE_PROP_RX = re.compile(r"\s*([a-z\-]+)\s*:\s*([^;]+?)\s*(?:;|$)")
_COLOR_VALUE_RX = re.compile(r"^#[0-9a-fA-F]{6}$")
_FONT_SIZE_VALUE_RX = re.compile(r"^(\d+)px$")


def _filter_span_style(value: str) -> str | None:
    """span의 style 속성을 화이트리스트 기반으로 정제.

    color는 프리셋 8색만, font-size는 프리셋 5단계 px만 통과시킨다.
    그 외 모든 CSS 프로퍼티(position, background, url(), expression() 등)는 제거.
    유효 프로퍼티가 하나도 없으면 None을 반환해 style 속성 자체를 떨어뜨린다.
    """
    if not value:
        return None
    kept: list[str] = []
    for match in _STYLE_PROP_RX.finditer(value):
        prop = match.group(1).lower()
        raw_val = match.group(2).strip()
        if prop == "color":
            if _COLOR_VALUE_RX.match(raw_val) and raw_val.lower() in _ALLOWED_COLORS:
                kept.append(f"color: {raw_val.lower()}")
        elif prop == "font-size":
            sz = _FONT_SIZE_VALUE_RX.match(raw_val)
            if sz and int(sz.group(1)) in _ALLOWED_FONT_SIZES_PX:
                kept.append(f"font-size: {sz.group(1)}px")
        # 그 외 프로퍼티는 무시
    if not kept:
        return None
    return "; ".join(kept)


def _attribute_filter(element: str, attribute: str, value: str) -> str | None:
    if element == "span" and attribute == "style":
        return _filter_span_style(value)
    return value


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
        attribute_filter=_attribute_filter,
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

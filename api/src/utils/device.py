"""접속 기기 판별 — User-Agent 문자열로 mobile/pc 를 대략 구분한다 (게시판 #141).

정밀 분류가 목적이 아니라 "연결 끊김이 모바일에서 잦은가 / PC에서 잦은가" 를 보기 위한
진단용이다. 애매한 경우(신형 iPadOS 가 데스크톱 UA 로 위장하는 등)는 감수한다.
"""

# UA(User-Agent, 브라우저가 보내는 기기·브라우저 식별 문자열)에 이 토큰이 있으면 모바일로 본다.
_MOBILE_TOKENS = (
    "Mobi",
    "Android",
    "iPhone",
    "iPod",
    "iPad",
    "Windows Phone",
    "IEMobile",
    "BlackBerry",
    "Opera Mini",
)


def classify_device(user_agent: str | None) -> str:
    """User-Agent → ``'mobile'`` | ``'pc'`` | ``'unknown'``.

    - UA 가 비었으면 'unknown' (판별 불가).
    - 모바일 토큰이 하나라도 있으면 'mobile'.
    - 그 외에는 'pc'.
    """
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    for token in _MOBILE_TOKENS:
        if token.lower() in ua:
            return "mobile"
    return "pc"

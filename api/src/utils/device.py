"""접속 기기 판별 — User-Agent 문자열로 mobile/pc 를 대략 구분한다 (게시판 #141).

정밀 분류가 목적이 아니라 "연결 끊김이 모바일에서 잦은가 / PC에서 잦은가" 를 보기 위한
진단용이다. 애매한 경우(신형 iPadOS 가 데스크톱 UA 로 위장하는 등)는 감수한다.
"""

import re

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


def mobile_ua_regex() -> str:
    """_MOBILE_TOKENS 를 SQL(Postgres) 정규식 한 줄로 만든다.

    접속 통계 집계(게시판 #144)는 UA 판별을 SQL 안에서 해야 해서 정규식이 필요하다.
    토큰 목록을 SQL 쪽에 다시 적어두면 파이썬(classify_device)과 결과가 갈라지므로,
    반드시 이 함수로 만들어 쓴다. 비교는 대소문자 무시(`~*`)로 해야
    classify_device 가 소문자로 낮춰 비교하는 것과 결과가 같아진다.
    """
    return "|".join(re.escape(token) for token in _MOBILE_TOKENS)


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

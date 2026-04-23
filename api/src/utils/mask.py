"""PII 마스킹 유틸리티."""


def mask_email(email: str) -> str:
    """이메일 주소를 부분 마스킹한다.

    로컬파트 ≥ 2자: 첫 글자 + '****' + '@도메인'
    로컬파트 ≤ 1자: '*****' + '@도메인'
    """
    if "@" not in email:
        return "*****"
    local, domain = email.split("@", 1)
    if len(local) >= 2:
        return f"{local[0]}****@{domain}"
    return f"*****@{domain}"

"""mask_email 유틸 단위 테스트."""

from api.src.utils.mask import mask_email


def test_mask_email_일반():
    assert mask_email("abcd@gmail.com") == "a****@gmail.com"


def test_mask_email_짧은_로컬파트_1자():
    assert mask_email("a@gmail.com") == "*****@gmail.com"


def test_mask_email_짧은_로컬파트_빈문자열():
    # 로컬파트 0자 (비정상 이메일이지만 방어 처리)
    assert mask_email("@gmail.com") == "*****@gmail.com"


def test_mask_email_2자_로컬():
    assert mask_email("ab@naver.com") == "a****@naver.com"


def test_mask_email_도메인_보존():
    result = mask_email("user@some-long-domain.co.kr")
    assert result.endswith("@some-long-domain.co.kr")


def test_mask_email_at_없음():
    result = mask_email("notanemail")
    assert result == "*****"

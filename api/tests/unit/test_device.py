"""classify_device 단위 테스트 (게시판 #141)."""

import pytest

from api.src.utils.device import classify_device


@pytest.mark.parametrize(
    "ua,expected",
    [
        # 모바일
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit", "mobile"),
        ("Mozilla/5.0 (Linux; Android 14; SM-S911N) AppleWebKit Mobile", "mobile"),
        ("Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X)", "mobile"),
        # PC
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit Chrome", "pc"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit Safari", "pc"),
        # 판별 불가
        (None, "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_device(ua, expected):
    assert classify_device(ua) == expected

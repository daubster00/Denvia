"""정적 Assertion 테스트 — vendor/rag/update_vectorstore.py drift 방지 (AC-5).

이 테스트가 실패하면 vendor/rag가 변경된 것 → ADR-0002 §결정 3 체크리스트 3문항을 PR 설명에 명시해야 머지 가능.
"""

import hashlib
from pathlib import Path

VENDOR_PARSER = (
    Path(__file__).parent.parent.parent.parent
    / "vendor"
    / "rag"
    / "update_vectorstore"
    / "update_vectorstore.py"
)

# 원본 파일이 변경되면 이 테스트가 깨지면서 reviewer에게 ADR-0002 §결정 3 체크리스트 수행을 강제.
# 갱신 절차: ① 변경 의도 PR 설명 명시 → ② reviewer가 3문항 검증 → ③ 본 상수 갱신.
EXPECTED_SHA256 = "37912f018475b5851ad0ba4b60e6629b537502b7533dad997749520ff269926d"


def test_parser_delimiters_preserved() -> None:
    """vendor 원본의 4개 구분자 패턴이 그대로 유지되는지 검증."""
    src = VENDOR_PARSER.read_text(encoding="utf-8")
    assert 'line.startswith("{")' in src, "대분류 시작 구분자 패턴 누락"
    assert 'line.endswith("}")' in src, "대분류 끝 구분자 패턴 누락"
    assert any(
        'line.startswith("=")' in line and 'line.endswith("=")' in line
        for line in src.splitlines()
    ), "중분류 구분자 동일 라인 검사 패턴 누락"
    assert 'line.strip("=")' in src, "중분류 라벨 추출 패턴 누락"


def test_parser_file_hash_unchanged() -> None:
    """vendor 원본 파일 해시 — drift 방지 (ADR-0002)."""
    src_bytes = VENDOR_PARSER.read_bytes()
    actual = hashlib.sha256(src_bytes).hexdigest()
    assert actual == EXPECTED_SHA256, (
        "vendor/rag/update_vectorstore drift detected — review against ADR-0002 §결정 3 "
        "(① 동일 입력→동일 출력, ② 동의어·룰 엔진 결과 동일, ③ 모델 파라미터 기본값 유지)."
    )

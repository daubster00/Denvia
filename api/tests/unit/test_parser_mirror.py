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
# 2026-09-14 갱신 (수정요청 게시판 #145) — 재구축 비용 집계.
#   변경 내용: update_vectorstore() 안에 인라인으로 있던 txt 파싱 루프를
#   build_documents(data_dir) 함수로 **한 글자도 바꾸지 않고** 분리하고,
#   update_vectorstore() 가 그 함수를 호출하도록만 바꿨다.
#   ADR-0002 §결정 3 체크리스트:
#     ① 동일 입력 → 동일 출력: 파싱 코드·page_content 조립·metadata 모두 동일,
#        호출 순서(vectorstore 삭제 → 파싱 → 임베딩 → save_local)도 동일. ✔
#     ② 동의어·룰 엔진 결과 동일: 파서를 건드리지 않았으므로 동일. ✔
#     ③ 모델 파라미터 기본값 유지: OpenAIEmbeddings(model="text-embedding-3-large") 그대로. ✔
#   분리 이유: 실제로 임베딩되는 텍스트를 OpenAI 추가 호출 없이 tiktoken 으로
#   세어 재구축 비용을 기록하기 위함(기존에는 임베딩 비용이 어디에도 안 남았음).
EXPECTED_SHA256 = "a6df2e1cc6c62fcf65918691e0fad69f50d59aa8dd09d0e31ffdc8238bc99308"


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


def test_update_vectorstore_uses_build_documents() -> None:
    """#145 — 비용 계산용 build_documents 가 실제 임베딩 경로와 같은 함수여야 한다.

    update_vectorstore() 가 자체 파싱 루프로 되돌아가면(= build_documents 미사용)
    비용 계산이 실제 임베딩 텍스트와 어긋나므로 여기서 막는다.
    """
    src = VENDOR_PARSER.read_text(encoding="utf-8")
    assert "def build_documents(" in src
    assert "documents = build_documents(data_dir)" in src
    # 파싱 루프는 build_documents 안에만 있어야 한다(중복 정의 금지).
    assert src.count('line.startswith("{")') == 1

"""dry_run_parse — vendor/rag/update_vectorstore.py의 파싱 단계만 mirror.

NFR-M2 준수: vendor/rag/ 코드를 import하지 않음.
drift 방지: tests/unit/test_parser_mirror.py가 원본 구분자 패턴 + 파일 SHA-256을 검증.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChunkPreview:
    category: str | None
    section: str
    char_count: int  # 실 텍스트는 보관하지 않음 (메모리·PII 최소화)


@dataclass
class CategoryGroup:
    major: str
    minors: list[str] = field(default_factory=list)


@dataclass
class ParseFailure:
    reason: str   # "no_categories" | "orphan_content" | "exception"
    message: str


@dataclass
class ParseResult:
    chunks: list[ChunkPreview]
    hierarchy: list[CategoryGroup]
    failure: ParseFailure | None
    chunk_count: int
    category_count: int


def dry_run_parse(file_path: Path | str) -> ParseResult:
    """vendor/rag/update_vectorstore.py의 파싱 단계만 mirror — 임베딩·FAISS 호출 0건.

    mirror 보존 항목 (update_vectorstore.py:51-99 인용):
    - line.strip() 우선 (line 51)
    - 대분류: line.startswith("{") and line.endswith("}"), 라벨 = line[1:-1] (line 56-57)
    - 중분류: line.startswith("=") and line.endswith("="), 라벨 = line.strip("=") (line 61, 78)
    - 마지막 section flush (line 86-98)
    - 빈 라인은 content_buffer에 추가하지 않음 (line 82)
    """
    path = Path(file_path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return ParseResult([], [], ParseFailure("exception", f"인코딩 오류: {e}"[:200]), 0, 0)
    except OSError as e:
        return ParseResult([], [], ParseFailure("exception", f"파일 읽기 오류: {e}"[:200]), 0, 0)

    chunks: list[ChunkPreview] = []
    groups: dict[str, list[str]] = {}  # major → minors (insertion order 보존)

    current_category: str | None = None
    current_section: str | None = None
    content_buffer: list[str] = []

    def _flush() -> None:
        if current_section and content_buffer:
            content = "\n".join(content_buffer)
            chunks.append(
                ChunkPreview(
                    category=current_category,
                    section=current_section,
                    char_count=len(f"{current_category}\n{current_section}\n{content}"),
                )
            )
            content_buffer.clear()

    has_any_content = False
    for raw in text.split("\n"):
        line = raw.strip()

        # 대분류 {대분류명} — vendor 원본 line 56-58
        if line.startswith("{") and line.endswith("}"):
            current_category = line[1:-1]
            groups.setdefault(current_category, [])
            continue

        # 중분류 =중분류명= (==이상도 strip("=")로 동일 매칭 — vendor 원본 line 61, 78)
        if line.startswith("=") and line.endswith("=") and len(line) >= 2:
            _flush()
            current_section = line.strip("=")
            if current_category is not None and current_section not in groups.get(current_category, []):
                groups.setdefault(current_category, []).append(current_section)
            continue

        if line:
            has_any_content = True
            content_buffer.append(line)

    # 마지막 section flush — vendor 원본 line 86-98
    _flush()

    chunk_count = len(chunks)
    category_count = len(groups)
    hierarchy = [CategoryGroup(major=k, minors=v) for k, v in groups.items()]

    if chunk_count == 0:
        if has_any_content and category_count == 0:
            return ParseResult(
                chunks,
                hierarchy,
                ParseFailure(
                    "orphan_content",
                    "내용이 있으나 분류 헤더가 없어 청크가 만들어지지 않았습니다.",
                ),
                0,
                0,
            )
        return ParseResult(
            chunks,
            hierarchy,
            ParseFailure(
                "no_categories",
                "지식 파일에 `{대분류}` 또는 `==중분류==` 구분자가 없습니다.",
            ),
            0,
            0,
        )

    return ParseResult(chunks, hierarchy, None, chunk_count, category_count)

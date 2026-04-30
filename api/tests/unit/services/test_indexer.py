"""dry_run_parse 단위 테스트 — Story 8.1 (AC-4)."""

import pytest
from pathlib import Path

from api.src.rag_integration.indexer import dry_run_parse


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


class TestDryRunParseHappyPath:
    def test_단일_대분류_단일_중분류(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "test.txt", "{보철}\n=크라운=\n크라운은 치아를 덮는 보철물이다.\n")
        result = dry_run_parse(f)
        assert result.failure is None
        assert result.chunk_count == 1
        assert result.category_count == 1
        assert result.hierarchy[0].major == "보철"
        assert result.hierarchy[0].minors == ["크라운"]

    def test_다중_대분류_다중_중분류(self, tmp_path: Path) -> None:
        content = (
            "{보철}\n=크라운=\n본문A\n=브릿지=\n본문B\n"
            "{근관치료}\n=급성치수염=\n본문C\n"
        )
        f = _write(tmp_path, "multi.txt", content)
        result = dry_run_parse(f)
        assert result.failure is None
        assert result.chunk_count == 3
        assert result.category_count == 2
        majors = [g.major for g in result.hierarchy]
        assert "보철" in majors and "근관치료" in majors

    def test_double_equal_중분류_strip(self, tmp_path: Path) -> None:
        """==중분류== 도 strip("=") 결과는 '중분류' — vendor 원본 동작 mirror."""
        f = _write(tmp_path, "double.txt", "{분류}\n==급성치수염==\n본문내용\n")
        result = dry_run_parse(f)
        assert result.failure is None
        assert result.hierarchy[0].minors[0] == "급성치수염"

    def test_마지막_section_flush_누락_방지(self, tmp_path: Path) -> None:
        """파일 끝에 newline이 없어도 마지막 청크가 생성된다."""
        f = _write(tmp_path, "noeol.txt", "{분류}\n=섹션=\n마지막줄")
        result = dry_run_parse(f)
        assert result.chunk_count == 1

    def test_char_count_계산(self, tmp_path: Path) -> None:
        content_text = "내용줄"
        f = _write(tmp_path, "char.txt", f"{{카테고리}}\n=섹션=\n{content_text}\n")
        result = dry_run_parse(f)
        expected = len(f"카테고리\n섹션\n{content_text}")
        assert result.chunks[0].char_count == expected


    def test_대분류_없이_중분류만_있으면_chunk_1개(self, tmp_path: Path) -> None:
        """=섹션=\n본문\n — vendor mirror: current_section and content_buffer면 category=None도 flush."""
        f = _write(tmp_path, "no_category.txt", "=섹션=\n본문줄\n")
        result = dry_run_parse(f)
        assert result.failure is None
        assert result.chunk_count == 1
        assert result.chunks[0].category is None
        # char_count은 vendor f"{current_category}\n..." 동작과 동일: "None\n섹션\n본문줄"
        assert result.chunks[0].char_count == len(f"{None}\n섹션\n본문줄")


class TestDryRunParseFailureCases:
    def test_빈_파일_no_categories(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "empty.txt", "")
        result = dry_run_parse(f)
        assert result.chunk_count == 0
        assert result.failure is not None
        assert result.failure.reason == "no_categories"

    def test_본문만_헤더_없음_orphan_content(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "orphan.txt", "헤더 없는 내용\n또 다른 내용\n")
        result = dry_run_parse(f)
        assert result.chunk_count == 0
        assert result.failure is not None
        assert result.failure.reason == "orphan_content"

    def test_비_utf8_예외_캡처(self, tmp_path: Path) -> None:
        p = tmp_path / "cp949.txt"
        p.write_bytes("한글CP949".encode("cp949"))
        result = dry_run_parse(p)
        assert result.chunk_count == 0
        assert result.failure is not None
        assert result.failure.reason == "exception"

    def test_존재하지_않는_파일_예외_캡처(self, tmp_path: Path) -> None:
        result = dry_run_parse(tmp_path / "nonexistent.txt")
        assert result.chunk_count == 0
        assert result.failure is not None
        assert result.failure.reason == "exception"

    def test_구분자만_있고_본문_없음_no_chunks(self, tmp_path: Path) -> None:
        f = _write(tmp_path, "notext.txt", "{분류}\n=섹션=\n")
        result = dry_run_parse(f)
        assert result.chunk_count == 0

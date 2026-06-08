"""테스트 mock factory에 current_session_id = None 일괄 추가.

배경: _enforce_session_match가 user.current_session_id를 검사하는데
MagicMock으로 만든 user는 이 속성이 자동으로 MagicMock 객체가 되어
JWT의 sid와 불일치 → 401 AUTH_SESSION_SUPERSEDED.

전략: def _make_<user|admin|... > ... return <var> 패턴을 찾아
return 직전에 <var>.current_session_id = None 삽입.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# def _make_*(...): ... return <var> 의 마지막 return을 찾는 정규식
FACTORY_RE = re.compile(
    r"^(?P<indent>[ \t]*)def\s+\w+\s*\(",
    re.MULTILINE,
)


def _find_function_block(text: str, start: int) -> tuple[int, int, str]:
    """함수 시작 위치(def 라인) → 함수 본문 끝 위치 및 본문 들여쓰기 반환.

    본문 indent를 첫 비어있지 않은 줄로 확정하고,
    그 indent 이상인 줄(또는 빈 줄)만 본문에 포함시킨다.
    """
    lines = text[start:].split("\n")
    body_indent = None
    pos = 0
    end_offset = 0
    for i, line in enumerate(lines):
        if i == 0:
            # def 라인 자체는 무조건 포함
            pos += len(line) + 1
            end_offset = pos
            continue
        # 빈 줄은 본문에 포함하고 계속
        if line.strip() == "":
            pos += len(line) + 1
            end_offset = pos
            continue
        # 현재 줄의 indent
        stripped = line.lstrip()
        cur_indent = line[: len(line) - len(stripped)]
        if body_indent is None:
            # 첫 비어있지 않은 줄 → 본문 indent로 확정
            body_indent = cur_indent
        # cur_indent가 body_indent보다 짧다면 함수 종료
        if len(cur_indent) < len(body_indent):
            break
        # body_indent를 prefix로 가져야 정상 — 아니라면 종료 (스페이스/탭 혼용 가드)
        if not cur_indent.startswith(body_indent):
            break
        pos += len(line) + 1
        end_offset = pos
    return start, start + end_offset, body_indent or "    "


RETURN_RE = re.compile(r"^(?P<indent>[ \t]+)return\s+(?P<var>\w+)\s*$", re.MULTILINE)


def _is_mock_factory(body: str) -> str | None:
    """함수 본문이 MagicMock을 만들어 속성 채우는 패턴이면 반환 변수명을 반환.

    감지 조건:
    - body에 `MagicMock()` 호출이 있음
    - body 끝 부분에 `return <var>` 라인이 있고, 그 var에 `.role` 또는 `.email` 등 속성이 할당됨
    """
    if "MagicMock(" not in body:
        return None
    last_return = None
    for m in RETURN_RE.finditer(body):
        last_return = m
    if last_return is None:
        return None
    var = last_return.group("var")
    # 그 변수에 속성이 할당된 적 있는지
    if re.search(rf"\b{re.escape(var)}\.(role|email|id|admin_grade)\s*=", body):
        return var
    return None


def fix_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    if "current_session_id" in text:
        return 0  # 이미 적용된 파일
    changed = 0
    # 모든 _make_* 함수에 대해 처리. 뒤에서부터 처리해야 offset이 안 어긋남.
    matches = list(FACTORY_RE.finditer(text))
    for m in reversed(matches):
        start = m.start()
        f_start, f_end, body_indent = _find_function_block(text, start)
        body = text[f_start:f_end]
        var = _is_mock_factory(body)
        if var is None:
            continue
        # 본문에서 마지막 `return <var>` 위치 찾기
        last_return = None
        for rm in RETURN_RE.finditer(body):
            if rm.group("var") == var:
                last_return = rm
        if last_return is None:
            continue
        # 이미 current_session_id 설정이 있으면 skip
        if re.search(rf"\b{re.escape(var)}\.current_session_id\s*=", body):
            continue
        # return 라인 직전에 삽입
        insert_pos = f_start + last_return.start()
        new_line = f"{last_return.group('indent')}{var}.current_session_id = None\n"
        text = text[:insert_pos] + new_line + text[insert_pos:]
        changed += 1
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: fix_test_mocks_session_id.py <test_dir>")
        return 1
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"Not a directory: {root}")
        return 1
    total_files = 0
    total_insertions = 0
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        inserted = fix_file(py)
        if inserted:
            total_files += 1
            total_insertions += inserted
            print(f"  + {py.relative_to(root)}: {inserted} factory(ies)")
    print(f"\nDone. files={total_files} insertions={total_insertions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

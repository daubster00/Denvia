"""테스트 mock factory에 admin_grade = "master" 일괄 추가.

배경: 관리자 API 라우터 다수가 `dependencies=[Depends(require_admin_page("/admin"))]`
또는 `Depends(require_admin_grade(...))`를 사용하는데, 이 가드들이 user.admin_grade를
검사한다. MagicMock으로 만든 user는 이 속성이 자동으로 MagicMock 객체가 되어
"master도 None도 아님" 분기로 떨어져 DB의 admin_grade_page_permissions 테이블을 추가
조회한다. 이게 mock side_effect의 call_count를 어긋나게 해서 budget/usage/anomaly 등
연쇄 실패.

전략: _make_user/_make_admin 등 mock factory의 return 직전에
<var>.admin_grade = "master" 삽입. master는 모든 페이지·등급 가드를 즉시 통과시키므로
추가 DB 쿼리가 발생하지 않는다.

current_session_id 패턴과 동일 — 이미 admin_grade 가 설정된 factory 는 skip.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


FACTORY_RE = re.compile(
    r"^(?P<indent>[ \t]*)def\s+\w+\s*\(",
    re.MULTILINE,
)


def _find_function_block(text: str, start: int) -> tuple[int, int, str]:
    lines = text[start:].split("\n")
    body_indent = None
    pos = 0
    end_offset = 0
    for i, line in enumerate(lines):
        if i == 0:
            pos += len(line) + 1
            end_offset = pos
            continue
        if line.strip() == "":
            pos += len(line) + 1
            end_offset = pos
            continue
        stripped = line.lstrip()
        cur_indent = line[: len(line) - len(stripped)]
        if body_indent is None:
            body_indent = cur_indent
        if len(cur_indent) < len(body_indent):
            break
        if not cur_indent.startswith(body_indent):
            break
        pos += len(line) + 1
        end_offset = pos
    return start, start + end_offset, body_indent or "    "


RETURN_RE = re.compile(r"^(?P<indent>[ \t]+)return\s+(?P<var>\w+)\s*$", re.MULTILINE)


def _is_mock_factory(body: str) -> str | None:
    if "MagicMock(" not in body:
        return None
    last_return = None
    for m in RETURN_RE.finditer(body):
        last_return = m
    if last_return is None:
        return None
    var = last_return.group("var")
    if re.search(rf"\b{re.escape(var)}\.(role|email|id|admin_grade)\s*=", body):
        return var
    return None


def fix_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    changed = 0
    matches = list(FACTORY_RE.finditer(text))
    for m in reversed(matches):
        start = m.start()
        f_start, f_end, body_indent = _find_function_block(text, start)
        body = text[f_start:f_end]
        var = _is_mock_factory(body)
        if var is None:
            continue
        # 이미 admin_grade 설정 있으면 skip
        if re.search(rf"\b{re.escape(var)}\.admin_grade\s*=", body):
            continue
        # role 이 "admin" 인 경우만 admin_grade 의미 있음 — user role 인 factory 는 skip
        # (단, role 이 변수면 모두 master 로 추가 — 해롭지 않음)
        # 보수적으로: role="admin" 명시된 경우만 추가
        role_match = re.search(rf'\b{re.escape(var)}\.role\s*=\s*["\']?(\w+)?["\']?', body)
        role_value = role_match.group(1) if role_match else None
        # role 이 user 변수거나 명시적으로 "admin" 인 경우만 추가
        # 단순화: 모든 factory에 추가 (user 라도 master 속성은 user role 가드에선 무시됨)
        last_return = None
        for rm in RETURN_RE.finditer(body):
            if rm.group("var") == var:
                last_return = rm
        if last_return is None:
            continue
        insert_pos = f_start + last_return.start()
        new_line = f'{last_return.group("indent")}{var}.admin_grade = "master"\n'
        text = text[:insert_pos] + new_line + text[insert_pos:]
        changed += 1
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: fix_test_mocks_admin_grade.py <test_dir>")
        return 1
    root = Path(sys.argv[1])
    if not root.is_dir():
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
            print(f"  + {py.relative_to(root)}: {inserted}")
    print(f"\nDone. files={total_files} insertions={total_insertions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""FAISS 이중 경로 원자 symlink 스왑 — Story 8.3 (AR7, NFR-R4)."""

import os
from pathlib import Path


def get_current_slot(
    current_symlink: str | Path,
    index_a_path: str | Path,
    index_b_path: str | Path,
) -> str | None:
    """현재 active slot 문자('a'|'b') 반환. symlink 없으면 None."""
    current = Path(current_symlink)
    if not current.is_symlink():
        return None
    resolved = current.resolve()
    if resolved == Path(index_a_path).resolve():
        return "a"
    if resolved == Path(index_b_path).resolve():
        return "b"
    return None


def atomic_swap(current_symlink: str | Path, target_path: str | Path) -> None:
    """current symlink을 target_path로 원자적으로 교체한다."""
    swap_faiss_index(str(target_path), str(current_symlink))


def swap_faiss_index(target: str, current_symlink: str) -> None:
    """current_symlink를 target을 가리키도록 원자적으로 교체한다.

    Story 2.1 기존 public 함수. init_faiss.py 회귀 방지를 위해 이름/인자 순서를 유지한다.
    링크 target은 Docker/WSL 호환을 위해 current_symlink 기준 상대 경로로 만든다.
    """
    current = Path(current_symlink)
    current.parent.mkdir(parents=True, exist_ok=True)
    link_dir = os.path.dirname(os.path.abspath(current_symlink))
    rel_target = os.path.relpath(target, link_dir)
    tmp_link = Path(f"{current_symlink}.tmp.{os.getpid()}")

    try:
        tmp_link.unlink(missing_ok=True)
        os.symlink(rel_target, tmp_link)
        try:
            os.replace(tmp_link, current)  # atomic on POSIX
        except (PermissionError, FileExistsError):
            # Windows fallback: non-atomic (dev-only; production is Linux)
            current.unlink(missing_ok=True)
            os.rename(tmp_link, current)
    except Exception:
        tmp_link.unlink(missing_ok=True)
        raise

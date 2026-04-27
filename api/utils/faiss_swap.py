"""FAISS 인덱스 원자적 교체 유틸리티 — zero-downtime swap."""

import os


def swap_faiss_index(target: str, current_symlink: str) -> None:
    """current_symlink를 target을 가리키도록 원자적으로 교체한다.

    os.rename은 Linux에서 기존 파일/심볼릭링크를 원자적으로 교체한다.
    """
    abs_target = os.path.abspath(target)
    tmp_link = current_symlink + ".tmp"

    if os.path.islink(tmp_link) or os.path.exists(tmp_link):
        os.unlink(tmp_link)

    os.symlink(abs_target, tmp_link)
    os.rename(tmp_link, current_symlink)

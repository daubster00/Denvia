"""FAISS 인덱스 원자적 교체 유틸리티 — zero-downtime swap."""

import os


def swap_faiss_index(target: str, current_symlink: str) -> None:
    """current_symlink를 target을 가리키도록 원자적으로 교체한다.

    os.rename은 Linux에서 기존 파일/심볼릭링크를 원자적으로 교체한다.

    링크 target은 같은 디렉터리 안의 형제 디렉터리를 가리키도록 **상대 경로**로 만든다.
    절대 경로로 만들면 Git Bash(MSYS `/d/...`)에서 생성한 링크가 Linux 컨테이너에서
    broken symlink로 보여 Docker 빌드 컨텍스트 수집이 실패한다.
    """
    link_dir = os.path.dirname(os.path.abspath(current_symlink))
    rel_target = os.path.relpath(target, link_dir)
    tmp_link = current_symlink + ".tmp"

    if os.path.islink(tmp_link) or os.path.exists(tmp_link):
        os.unlink(tmp_link)

    os.symlink(rel_target, tmp_link)
    os.rename(tmp_link, current_symlink)

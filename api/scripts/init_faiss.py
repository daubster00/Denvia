"""FAISS 이중 인덱스 초기화 스크립트.

index_a에 시드 데이터로 벡터스토어를 빌드하고,
current → index_a 심볼릭 링크를 원자적으로 생성한다.

실행: cd api && uv run python scripts/init_faiss.py
전제조건: OPENAI_API_KEY 환경변수 설정
"""

import os
import sys

# 어떤 cwd에서 실행해도 동일하게 동작하도록 양쪽 경로 모두 sys.path에 추가
API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(API_DIR)
VENDOR_DIR = os.path.join(PROJECT_ROOT, "vendor")
sys.path.insert(0, VENDOR_DIR)       # rag.* 패키지 import용
sys.path.insert(0, PROJECT_ROOT)     # api.utils.* 패키지 import용

from rag.update_vectorstore import update_vectorstore
from api.utils.faiss_swap import swap_faiss_index


INDEX_A = "data/faiss/index_a"
INDEX_B = "data/faiss/index_b"
CURRENT = "data/faiss/current"
SEED_DIR = os.path.join(VENDOR_DIR, "rag", "data", "seed")


def main():
    os.makedirs(INDEX_A, exist_ok=True)
    os.makedirs(INDEX_B, exist_ok=True)

    print("🔨 index_a 빌드 중...")
    update_vectorstore(data_dir=SEED_DIR, vector_path=INDEX_A)

    print("🔗 current → index_a 심볼릭 링크 생성 중...")
    swap_faiss_index(INDEX_A, CURRENT)
    print(f"✅ FAISS 초기화 완료: {os.path.realpath(CURRENT)}")


if __name__ == "__main__":
    main()

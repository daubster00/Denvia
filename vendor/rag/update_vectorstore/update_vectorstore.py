from dotenv import load_dotenv
load_dotenv()

import os
import glob
import shutil

from langchain_core.documents import Document  # langchain 1.2+ 호환 (구 langchain.schema에서 이동, 동일 클래스)
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS


# ADR-0002 허용 수정 (i)(ii): top-level 즉시 실행 → 함수형 entry 재구성 + 경로 주입
def update_vectorstore(data_dir=None, vector_path=None):
    """txt 파일을 읽어 FAISS 벡터스토어를 빌드한다.

    Args:
        data_dir: txt 파일이 있는 디렉터리. 환경변수 VECTORSTORE_DATA_DIR 또는 'data' 기본값.
        vector_path: FAISS 인덱스를 저장할 경로. 환경변수 FAISS_TARGET_PATH 또는 'vectorstore/faiss_index' 기본값.
    """
    if data_dir is None:
        data_dir = os.environ.get("VECTORSTORE_DATA_DIR", "data")
    if vector_path is None:
        vector_path = os.environ.get("FAISS_TARGET_PATH", "vectorstore/faiss_index")

    # 🔥 vectorstore 초기화 (자동 삭제)
    if os.path.exists(vector_path):
        print("🧹 기존 vectorstore 삭제 중...")
        shutil.rmtree(vector_path)

    txt_files = sorted(glob.glob(os.path.join(data_dir, "*.txt")))

    if not txt_files:
        raise FileNotFoundError(f"❌ txt 파일이 없습니다: {data_dir}")

    documents = []

    for file_path in txt_files:

        file_name = os.path.basename(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        lines = text.split("\n")

        current_category = None
        current_section = None
        content_buffer = []

        for line in lines:

            line = line.strip()

            # ✅ 대제목 { }
            if line.startswith("{") and line.endswith("}"):
                current_category = line[1:-1]
                continue

            # ✅ 중분류 = =
            if line.startswith("=") and line.endswith("="):

                if current_section and content_buffer:
                    content = "\n".join(content_buffer)

                    documents.append(
                        Document(
                            page_content=f"{current_category}\n{current_section}\n{content}",
                            metadata={
                                "category": current_category,
                                "section": current_section,
                                "source": file_name
                            }
                        )
                    )
                    content_buffer = []

                current_section = line.strip("=")
                continue

            # ✅ 일반 내용
            if line:
                content_buffer.append(line)

        # ✅ 마지막 section 저장
        if current_section and content_buffer:
            content = "\n".join(content_buffer)

            documents.append(
                Document(
                    page_content=f"{current_category}\n{current_section}\n{content}",
                    metadata={
                        "category": current_category,
                        "section": current_section,
                        "source": file_name
                    }
                )
            )

    print("📄 document 수:", len(documents))

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    vectorstore = FAISS.from_documents(documents, embeddings)

    vectorstore.save_local(vector_path)

    print("✅ VectorStore 생성 완료")


if __name__ == "__main__":
    update_vectorstore()

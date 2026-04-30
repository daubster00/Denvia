"""KnowledgeUpload ORM 모델 sanity 테스트 — Story 8.1 (AC-1)."""

from api.src.models.knowledge_upload import (
    KnowledgeUpload,
    STATUS_ACTIVE,
    STATUS_DELETED,
    STATUS_REBUILD_PENDING,
    STATUS_VALIDATED,
)


class TestKnowledgeUploadModel:
    def test_tablename(self) -> None:
        assert KnowledgeUpload.__tablename__ == "knowledge_uploads"

    def test_status_constants(self) -> None:
        assert STATUS_VALIDATED == "validated"
        assert STATUS_REBUILD_PENDING == "rebuild_pending"
        assert STATUS_ACTIVE == "active"
        assert STATUS_DELETED == "deleted"

    def test_필수_컬럼_존재(self) -> None:
        cols = {c.key for c in KnowledgeUpload.__table__.columns}
        required = {
            "id", "filename", "original_path", "size_bytes", "content_hash",
            "chunk_count", "category_count", "hierarchy_json", "status",
            "uploaded_by_admin_id", "uploaded_at", "last_modified_at", "deleted_at",
        }
        assert required.issubset(cols), f"누락된 컬럼: {required - cols}"

    def test_content_hash_길이_64(self) -> None:
        col = KnowledgeUpload.__table__.c.content_hash
        assert col.type.length == 64

    def test_status_길이_20(self) -> None:
        col = KnowledgeUpload.__table__.c.status
        assert col.type.length == 20

    def test_인덱스_존재(self) -> None:
        index_names = {idx.name for idx in KnowledgeUpload.__table__.indexes}
        assert "idx_knowledge_uploads_content_hash" in index_names
        assert "idx_knowledge_uploads_status_uploaded_at" in index_names

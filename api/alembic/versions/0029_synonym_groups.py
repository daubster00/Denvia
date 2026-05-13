"""Story 8.5 — synonym_groups 테이블 + vendor/rag 시드 INSERT.

vendor/rag/run_qa/config/synonyms.json(226 그룹)을 DB SSOT로 외부화한다.
관리자가 web UI에서 추가/수정/삭제/CSV import 시 즉시 다음 RAG 호출에 반영.

Schema:
- id BIGSERIAL PK
- canonical_term VARCHAR(100) UNIQUE NOT NULL
- synonyms JSONB NOT NULL DEFAULT '[]'::jsonb
- created_by_admin_id BIGINT FK→users.id ON DELETE SET NULL NULL
- updated_by_admin_id BIGINT FK→users.id ON DELETE SET NULL NULL
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
- updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indexes:
- uq_synonym_groups_canonical_term UNIQUE
- ix_synonym_groups_canonical_term_trgm GIN trigram (pg_trgm은 0020에서 활성화됨)

시드(멱등): synonym_groups 행이 0인 경우에만 vendor/rag/run_qa/config/synonyms.json
INSERT. 파일이 없으면 warning 로그 + skip.

down_revision='0028_killswitch_extra_cols'.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "0029_synonym_groups"
down_revision = "0028_killswitch_extra_cols"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _seed_from_vendor(bind) -> None:
    """vendor/rag/run_qa/config/synonyms.json을 SELECT count = 0일 때만 INSERT."""
    count = bind.execute(sa.text("SELECT COUNT(*) FROM synonym_groups")).scalar()
    if count and int(count) > 0:
        logger.info("synonym_groups.seed.skipped existing_rows=%s", count)
        return

    # alembic 마이그레이션 실행 위치는 api/ 또는 /workspace/api. project root로 거슬러 올라가야 함.
    candidates = [
        Path(__file__).resolve().parents[3] / "vendor/rag/run_qa/config/synonyms.json",
        Path("/workspace/vendor/rag/run_qa/config/synonyms.json"),
        Path.cwd() / "vendor/rag/run_qa/config/synonyms.json",
    ]
    seed_file: Path | None = next((p for p in candidates if p.exists()), None)

    if seed_file is None:
        logger.warning(
            "synonym_groups.seed.skipped reason=vendor_file_missing tried=%s",
            [str(p) for p in candidates],
        )
        return

    try:
        raw = seed_file.read_text(encoding="utf-8")
        data: dict[str, list[str]] = json.loads(raw)
    except Exception as exc:
        logger.warning("synonym_groups.seed.skipped reason=parse_error error=%s", exc)
        return

    inserted = 0
    for canonical, synonyms in data.items():
        canonical = (canonical or "").strip()
        if not canonical:
            continue
        # 동의어 정제: trim, 빈 항목 제거, 자기참조 제거, 중복 제거(순서 보존)
        seen: set[str] = set()
        cleaned: list[str] = []
        for s in synonyms or []:
            s_norm = (s or "").strip()
            if not s_norm or s_norm == canonical or s_norm in seen:
                continue
            seen.add(s_norm)
            cleaned.append(s_norm)

        bind.execute(
            sa.text(
                "INSERT INTO synonym_groups (canonical_term, synonyms) "
                "VALUES (:term, CAST(:syns AS JSONB)) "
                "ON CONFLICT (canonical_term) DO NOTHING"
            ),
            {"term": canonical, "syns": json.dumps(cleaned, ensure_ascii=False)},
        )
        inserted += 1

    logger.info("synonym_groups.seed.completed inserted=%s file=%s", inserted, seed_file)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS synonym_groups (
            id BIGSERIAL PRIMARY KEY,
            canonical_term VARCHAR(100) NOT NULL,
            synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by_admin_id BIGINT NULL,
            updated_by_admin_id BIGINT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        "ALTER TABLE synonym_groups "
        "DROP CONSTRAINT IF EXISTS uq_synonym_groups_canonical_term"
    )
    op.execute(
        "ALTER TABLE synonym_groups "
        "ADD CONSTRAINT uq_synonym_groups_canonical_term UNIQUE (canonical_term)"
    )

    op.execute(
        "ALTER TABLE synonym_groups "
        "DROP CONSTRAINT IF EXISTS fk_synonym_groups_created_by"
    )
    op.execute(
        "ALTER TABLE synonym_groups "
        "ADD CONSTRAINT fk_synonym_groups_created_by "
        "FOREIGN KEY (created_by_admin_id) REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE synonym_groups "
        "DROP CONSTRAINT IF EXISTS fk_synonym_groups_updated_by"
    )
    op.execute(
        "ALTER TABLE synonym_groups "
        "ADD CONSTRAINT fk_synonym_groups_updated_by "
        "FOREIGN KEY (updated_by_admin_id) REFERENCES users(id) ON DELETE SET NULL"
    )

    # pg_trgm 확장은 0020에서 이미 활성화됨. IF NOT EXISTS GIN 인덱스만 생성.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_synonym_groups_canonical_term_trgm "
        "ON synonym_groups USING GIN (canonical_term gin_trgm_ops)"
    )

    bind = op.get_bind()
    _seed_from_vendor(bind)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_synonym_groups_canonical_term_trgm")
    op.execute("DROP TABLE IF EXISTS synonym_groups")
    # pg_trgm extension은 다른 스토리(6.1)가 소유 — 보존.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/layout/ConfirmDialog";
import {
  createSynonymGroup,
  fetchSynonyms,
  type SynonymGroupInput,
} from "@/features/admin-rag/api/synonyms";
import { SynonymGroupForm } from "@/features/admin-rag/components/SynonymGroupForm";
import { SynonymGroupRow } from "@/features/admin-rag/components/SynonymGroupRow";
import { SynonymImportExport } from "@/features/admin-rag/components/SynonymImportExport";
import styles from "./page.module.css";

const PAGE_SIZE = 20;

export default function SynonymsPage() {
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [confirmCreate, setConfirmCreate] = useState<SynonymGroupInput | null>(null);
  const qc = useQueryClient();

  // 250ms debounce
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(qInput.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [qInput]);

  const listQuery = useQuery({
    queryKey: ["admin-rag-synonyms", { q, page }],
    queryFn: () => fetchSynonyms({ q: q || undefined, page, size: PAGE_SIZE }),
    staleTime: 30_000,
  });

  const occupiedTerms = useMemo(() => {
    const m = new Map<string, { id: number; canonicalTerm: string }>();
    for (const g of listQuery.data?.groups ?? []) {
      m.set(g.canonical_term, { id: g.id, canonicalTerm: g.canonical_term });
      for (const s of g.synonyms) {
        if (!m.has(s)) m.set(s, { id: g.id, canonicalTerm: g.canonical_term });
      }
    }
    return m;
  }, [listQuery.data]);

  const createMut = useMutation({
    mutationFn: (data: SynonymGroupInput) => createSynonymGroup(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-rag-synonyms"] });
      setCreating(false);
      setConfirmCreate(null);
    },
  });

  const totalPages = listQuery.data
    ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE))
    : 1;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.heading}>동의어 데이터</h1>
          <p className={styles.subheading}>
            대표어와 동의어를 관리합니다. 변경 시 약 1초 내 RAG 응답에 반영됩니다.
          </p>
        </div>
      </div>

      <div className={styles.toolbar}>
        <input
          type="search"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="대표어 또는 동의어 검색"
          className={styles.search}
        />
        <button
          type="button"
          className={styles.primaryBtn}
          onClick={() => setCreating(true)}
          disabled={creating}
        >
          + 새 그룹
        </button>
        <SynonymImportExport />
      </div>

      {creating && (
        <div className={styles.createBox}>
          <h2 className={styles.boxTitle}>새 그룹</h2>
          <SynonymGroupForm
            occupiedTerms={occupiedTerms}
            submitting={createMut.isPending}
            error={
              createMut.isError && createMut.error instanceof Error
                ? createMut.error.message === "SYNONYM_CONFLICT"
                  ? "이미 다른 그룹에서 사용 중인 표현이 있습니다."
                  : "저장에 실패했습니다."
                : null
            }
            onSubmit={(data) => setConfirmCreate(data)}
            onCancel={() => setCreating(false)}
            submitLabel="추가"
          />
        </div>
      )}

      <div className={styles.tableHeader}>
        <span>대표어</span>
        <span>동의어</span>
        <span className={styles.actionsHeader}>액션</span>
      </div>

      <div className={styles.list}>
        {listQuery.isLoading && <p className={styles.statusText}>불러오는 중...</p>}
        {listQuery.isError && (
          <p className={styles.errorText}>목록을 불러오지 못했습니다.</p>
        )}
        {listQuery.data?.groups.length === 0 && (
          <p className={styles.statusText}>검색 결과가 없습니다.</p>
        )}
        {listQuery.data?.groups.map((g) => (
          <SynonymGroupRow key={g.id} group={g} occupiedTerms={occupiedTerms} />
        ))}
      </div>

      {listQuery.data && listQuery.data.total > PAGE_SIZE && (
        <div className={styles.pagination}>
          <button
            type="button"
            className={styles.pageBtn}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            이전
          </button>
          <span className={styles.pageInfo}>
            {page} / {totalPages} (총 {listQuery.data.total}개)
          </span>
          <button
            type="button"
            className={styles.pageBtn}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            다음
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmCreate !== null}
        title="동의어 그룹 저장"
        description="이 변경은 약 1초 내 모든 신규 질문에 반영됩니다. 진행하시겠습니까?"
        confirmLabel="저장"
        onConfirm={() => confirmCreate && createMut.mutate(confirmCreate)}
        onCancel={() => setConfirmCreate(null)}
      />
    </div>
  );
}

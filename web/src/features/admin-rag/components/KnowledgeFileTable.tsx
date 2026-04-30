"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchKnowledgeList, KnowledgeListItem } from "../api/knowledge";
import styles from "./KnowledgeFileTable.module.css";

function formatKst(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    validated: { label: "재벡터화 대기", className: styles.badgeWarning },
    rebuild_pending: { label: "재빌드 대기", className: styles.badgeWarning },
    active: { label: "활성", className: styles.badgeSuccess },
    deleted: { label: "삭제됨", className: styles.badgeNeutral },
  };
  const info = map[status] ?? { label: status, className: styles.badgeNeutral };
  return <span className={`${styles.badge} ${info.className}`}>{info.label}</span>;
}

interface Props {
  refreshSignal?: number;
  onHighlight?: (id: number) => void;
  highlightId?: number;
  onValidatedCountChange?: (count: number) => void;
  onEdit?: (id: number) => void;
  onDelete?: (item: KnowledgeListItem) => void;
}

const PER_PAGE = 20;

export function KnowledgeFileTable({ refreshSignal, onHighlight, highlightId, onValidatedCountChange, onEdit, onDelete }: Props) {
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-rag-knowledge", page, refreshSignal],
    queryFn: () => fetchKnowledgeList(page, PER_PAGE),
  });

  useEffect(() => {
    if (data && onValidatedCountChange) {
      onValidatedCountChange(data.items.filter((i) => i.status === "validated").length);
    }
  }, [data, onValidatedCountChange]);

  if (isLoading) {
    return <div className={styles.empty}>로딩 중…</div>;
  }

  if (isError || !data) {
    return <div className={styles.empty}>데이터를 불러오지 못했습니다.</div>;
  }

  if (data.total === 0) {
    return (
      <div className={styles.emptyState}>
        <span>📄</span>
        <p>첫 TXT 파일을 업로드해보세요</p>
      </div>
    );
  }

  const totalPages = Math.ceil(data.total / PER_PAGE);

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>파일명</th>
            <th>업로드일</th>
            <th>청크 수</th>
            <th>분류 수</th>
            <th>상태</th>
            <th>작업</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: KnowledgeListItem) => (
            <tr
              key={item.id}
              className={item.id === highlightId ? styles.highlighted : undefined}
            >
              <td>{item.filename}</td>
              <td>{formatKst(item.uploaded_at)}</td>
              <td>{item.chunk_count ?? "—"}</td>
              <td>{item.category_count ?? "—"}</td>
              <td>
                <StatusBadge status={item.status} />
              </td>
              <td>
                <button
                  type="button"
                  onClick={() => onEdit?.(item.id)}
                  className={styles.actionBtn}
                >
                  편집
                </button>
                <button
                  type="button"
                  onClick={() => onDelete?.(item)}
                  className={styles.actionBtn}
                >
                  삭제
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className={styles.pagination}>
          <button
            type="button"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
            className={styles.pageBtn}
          >
            이전
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPage(p)}
              className={`${styles.pageBtn} ${p === page ? styles.pageBtnActive : ""}`}
            >
              {p}
            </button>
          ))}
          <button
            type="button"
            disabled={page === totalPages}
            onClick={() => setPage((p) => p + 1)}
            className={styles.pageBtn}
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
}

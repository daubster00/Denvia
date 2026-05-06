"use client";

import { useState } from "react";
import type { AuditLogItem } from "@/features/admin-users/api/audit";
import {
  formatAuditAction,
  formatDiffField,
  formatDiffValue,
} from "@/features/admin-users/labels";
import styles from "./UserEditHistoryTable.module.css";

interface Props {
  items: AuditLogItem[];
  page: number;
  perPage: number;
  total: number;
  isLoading: boolean;
  isError: boolean;
  onPageChange: (page: number) => void;
  onSelect: (log: AuditLogItem) => void;
  onResetFilters: () => void;
}

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDate(value: string): string {
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

function summarizeDiff(diff: Record<string, unknown> | null): {
  fields: string;
  before_after: string;
} {
  if (!diff) return { fields: "—", before_after: "—" };
  const before = (diff.before ?? {}) as Record<string, unknown>;
  const after = (diff.after ?? {}) as Record<string, unknown>;
  const allKeys = Array.from(
    new Set([...Object.keys(before), ...Object.keys(after)]),
  );
  const fields = allKeys.map(formatDiffField).join(", ") || "—";
  // 단일 필드면 "before → after" 그대로, 복수면 첫 필드만 요약
  if (allKeys.length === 0) return { fields: "—", before_after: "—" };
  const firstKey = allKeys[0];
  const beforeVal = formatDiffValue(firstKey, before[firstKey]);
  const afterVal = formatDiffValue(firstKey, after[firstKey]);
  const more = allKeys.length > 1 ? ` 외 ${allKeys.length - 1}건` : "";
  return {
    fields,
    before_after: `${beforeVal} → ${afterVal}${more}`,
  };
}

export function UserEditHistoryTable({
  items,
  page,
  perPage,
  total,
  isLoading,
  isError,
  onPageChange,
  onSelect,
  onResetFilters,
}: Props) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  if (isError) {
    return (
      <div className={styles.errorBox} role="alert">
        이력을 불러오지 못했습니다.
      </div>
    );
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className={styles.emptyBox} role="status">
        <p className={styles.emptyTitle}>수정 이력이 없습니다</p>
        <p className={styles.emptySubtitle}>필터를 조정해보세요</p>
        <button
          type="button"
          onClick={onResetFilters}
          className={styles.resetButton}
        >
          필터 초기화
        </button>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <table className={styles.table} data-testid="user-edit-history-table">
        <thead>
          <tr>
            <th>수정 일시</th>
            <th>대상 사용자</th>
            <th>액션</th>
            <th>변경 필드</th>
            <th>이전 → 이후</th>
            <th>관리자</th>
            <th>상세</th>
          </tr>
        </thead>
        <tbody>
          {isLoading
            ? Array.from({ length: Math.min(perPage, 5) }).map((_, i) => (
                <tr key={`skeleton-${i}`} className={styles.skeletonRow}>
                  <td colSpan={7}>
                    <div className={styles.skeletonBar} />
                  </td>
                </tr>
              ))
            : items.map((log) => {
                const summary = summarizeDiff(log.diff_json);
                const isSystem = log.action === "user.block_auto_expired";
                const targetLabel =
                  log.target_email && log.target_id !== null
                    ? `${log.target_email} (ID ${log.target_id})`
                    : log.target_id !== null
                      ? `(ID ${log.target_id})`
                      : "—";
                return (
                  <tr key={log.id} data-testid={`audit-row-${log.id}`}>
                    <td>{formatDate(log.created_at)}</td>
                    <td>{targetLabel}</td>
                    <td>
                      <span className={styles.actionLabel}>
                        {formatAuditAction(log.action)}
                      </span>
                    </td>
                    <td>{summary.fields}</td>
                    <td className={styles.diffSummary}>
                      {summary.before_after}
                    </td>
                    <td>
                      {isSystem
                        ? "시스템 자동"
                        : log.actor_email ?? `(ID ${log.actor_user_id})`}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={styles.detailButton}
                        onClick={() => onSelect(log)}
                        data-testid={`audit-detail-button-${log.id}`}
                      >
                        보기
                      </button>
                    </td>
                  </tr>
                );
              })}
        </tbody>
      </table>

      {totalPages > 1 ? (
        <nav className={styles.pagination} aria-label="페이지네이션">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className={styles.pageButton}
          >
            이전
          </button>
          <span className={styles.pageInfo}>
            {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className={styles.pageButton}
          >
            다음
          </button>
        </nav>
      ) : null}
    </div>
  );
}

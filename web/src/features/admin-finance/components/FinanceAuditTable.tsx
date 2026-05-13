"use client";

import type { AuditLogItem } from "@/features/admin-users/api/audit";
import {
  formatFinanceAuditAction,
  getFinanceAuditActionTone,
  parseFinanceAuditDiff,
} from "@/features/admin-finance/labels";
import styles from "./FinanceAuditTable.module.css";

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

function formatKrw(amount: number | null): string {
  if (amount === null) return "—";
  return `₩${amount.toLocaleString("ko-KR")}`;
}

const TONE_CLASS: Record<string, string> = {
  approve: styles.actionApprove,
  deny: styles.actionDeny,
  extend: styles.actionExtend,
  generic: styles.actionGeneric,
};

export function FinanceAuditTable({
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
        감사 로그를 불러오지 못했습니다.
      </div>
    );
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className={styles.emptyBox} role="status">
        <p className={styles.emptyTitle}>해당 조건의 감사 로그가 없습니다</p>
        <p className={styles.emptySubtitle}>액션 필터를 조정해보세요</p>
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
      <table className={styles.table} data-testid="finance-audit-table">
        <thead>
          <tr>
            <th>시각</th>
            <th>액션</th>
            <th>금액</th>
            <th>결제 ID</th>
            <th>환불 큐 / 구독 ID</th>
            <th>사유</th>
            <th>관리자</th>
            <th>상세</th>
          </tr>
        </thead>
        <tbody>
          {isLoading
            ? Array.from({ length: Math.min(perPage, 5) }).map((_, i) => (
                <tr key={`skeleton-${i}`} className={styles.skeletonRow}>
                  <td colSpan={8}>
                    <div className={styles.skeletonBar} />
                  </td>
                </tr>
              ))
            : items.map((log) => {
                const parsed = parseFinanceAuditDiff(log.action, log.diff_json);
                const tone = getFinanceAuditActionTone(log.action);
                const isSystem = log.actor_user_id === 0 || log.actor_user_id === null;
                return (
                  <tr key={log.id} data-testid={`finance-audit-row-${log.id}`}>
                    <td>{formatDate(log.created_at)}</td>
                    <td>
                      <span
                        className={`${styles.actionBadge} ${TONE_CLASS[tone] ?? styles.actionGeneric}`}
                      >
                        {formatFinanceAuditAction(log.action)}
                      </span>
                    </td>
                    <td className={styles.amount}>{formatKrw(parsed.amountKrw)}</td>
                    <td>
                      {parsed.paymentId !== null ? `#${parsed.paymentId}` : <span className={styles.muted}>—</span>}
                    </td>
                    <td>
                      {log.target_id !== null ? `#${log.target_id}` : <span className={styles.muted}>—</span>}
                    </td>
                    <td>{parsed.reasonLabel ?? <span className={styles.muted}>—</span>}</td>
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
                        data-testid={`finance-audit-detail-${log.id}`}
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

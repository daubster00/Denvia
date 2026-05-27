"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchWatchedAccounts,
  type WatchedAccountListResponse,
} from "@/features/admin-anomaly/api/anomaly";
import { useRemoveWatch } from "@/features/admin-anomaly/hooks/useWatchToggle";
import { AnomalyDetailDrawer } from "@/features/admin-anomaly/components/AnomalyDetailDrawer";
import { formatAnomalyType } from "@/features/admin-users/labels";
import styles from "./page.module.css";

const PER_PAGE = 30;

const KST_FORMAT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_FORMAT.format(new Date(value));
  } catch {
    return value;
  }
}

function formatStatus(item: {
  user_blocked_now: boolean;
  user_auto_throttled_now: boolean;
  user_subscription_status: "free" | "pro" | "blocked" | null;
}): { label: string; tone: "danger" | "warning" | "muted" | "ok" } {
  if (item.user_blocked_now) return { label: "차단", tone: "danger" };
  if (item.user_auto_throttled_now) return { label: "자동제한", tone: "warning" };
  if (item.user_subscription_status === "pro")
    return { label: "Pro · 정상", tone: "ok" };
  if (item.user_subscription_status === "free")
    return { label: "무료 · 정상", tone: "ok" };
  return { label: "—", tone: "muted" };
}

export default function WatchedAccountsPage() {
  const [page, setPage] = useState(1);
  const [openedAnomalyId, setOpenedAnomalyId] = useState<number | null>(null);
  const { data, isLoading, isError, refetch } =
    useQuery<WatchedAccountListResponse>({
      queryKey: ["admin", "anomaly", "watched", { page, per_page: PER_PAGE }],
      queryFn: () => fetchWatchedAccounts({ page, per_page: PER_PAGE }),
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    });
  const removeWatch = useRemoveWatch();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = total === 0 ? 1 : Math.ceil(total / PER_PAGE);

  function handleRemove(userId: number) {
    removeWatch.mutate({ userId });
  }

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>주의 계정</h1>
        <p className={styles.caption}>
          이상탐지 항목에서 별 모양 버튼으로 등록된 계정 목록입니다. 최근 등록 순으로 표시됩니다.
        </p>
      </header>

      <div className={styles.controls}>
        <span className={styles.totalLabel}>총 {total}건</span>
        <button
          type="button"
          className={styles.refreshButton}
          onClick={() => refetch()}
          disabled={isLoading}
        >
          새로고침
        </button>
      </div>

      {isError ? (
        <div className={styles.errorBox} role="alert">
          <p className={styles.errorText}>주의 계정 목록을 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryButton}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </div>
      ) : !isLoading && items.length === 0 ? (
        <div className={styles.emptyBox} role="status">
          <p className={styles.emptyTitle}>등록된 주의 계정이 없습니다.</p>
          <p className={styles.emptyHint}>
            이상탐지 페이지에서 별 모양 버튼을 눌러 계정을 등록하세요.
          </p>
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table} role="table" aria-busy={isLoading}>
            <thead className={styles.thead}>
              <tr>
                <th scope="col" className={styles.colNo}>
                  No
                </th>
                <th scope="col">계정명</th>
                <th scope="col">이상탐지 항목</th>
                <th scope="col">현재 상태</th>
                <th scope="col">등록일시</th>
                <th scope="col">상세보기</th>
                <th scope="col" aria-label="주의 계정 해제">
                  해제
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                const status = formatStatus(item);
                const rowNumber = (page - 1) * PER_PAGE + idx + 1;
                const anomalies = item.anomalies ?? [];
                return (
                  <tr key={item.user_id} className={styles.row}>
                    <td className={styles.colNo}>{rowNumber}</td>
                    <td>
                      <Link
                        href={`/admin/users/${item.user_id}`}
                        className={styles.userLink}
                      >
                        {item.email_masked ?? `#${item.user_id}`}
                      </Link>
                    </td>
                    <td>
                      {anomalies.length === 0 ? (
                        "—"
                      ) : (
                        <ul className={styles.anomalyList}>
                          {anomalies.map((a) => (
                            <li
                              key={a.anomaly_id}
                              className={styles.anomalyItem}
                            >
                              {formatAnomalyType(a.type)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>
                      <span
                        className={
                          status.tone === "danger"
                            ? styles.statusDanger
                            : status.tone === "warning"
                              ? styles.statusWarning
                              : status.tone === "ok"
                                ? styles.statusOk
                                : styles.statusMuted
                        }
                      >
                        {status.label}
                      </span>
                    </td>
                    <td>{formatDateTime(item.flagged_at)}</td>
                    <td>
                      {anomalies.length === 0 ? (
                        <span className={styles.statusMuted}>—</span>
                      ) : (
                        <ul className={styles.anomalyList}>
                          {anomalies.map((a) => (
                            <li
                              key={a.anomaly_id}
                              className={styles.anomalyItem}
                            >
                              <button
                                type="button"
                                className={styles.detailButton}
                                onClick={() => setOpenedAnomalyId(a.anomaly_id)}
                              >
                                상세보기
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className={`${styles.starButton} ${styles.starIcon} ${styles.starActive}`}
                        aria-pressed="true"
                        aria-label="주의 계정 해제"
                        title="주의 계정 해제"
                        onClick={() => handleRemove(item.user_id)}
                        disabled={removeWatch.isPending}
                      >
                        ★
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <nav className={styles.pagination} aria-label="페이지 네비게이션">
            <button
              type="button"
              className={styles.pageButton}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || isLoading}
            >
              이전
            </button>
            <span className={styles.pageLabel} aria-live="polite">
              {page} / {totalPages}
            </span>
            <button
              type="button"
              className={styles.pageButton}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isLoading}
            >
              다음
            </button>
          </nav>
        </div>
      )}

      {openedAnomalyId !== null ? (
        <AnomalyDetailDrawer
          anomalyId={openedAnomalyId}
          onClose={() => setOpenedAnomalyId(null)}
        />
      ) : null}
    </section>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchSubscribers,
  type PendingCancellation,
} from "@/features/admin-dashboard/api/analytics";
import { SubscribersDonut } from "@/features/admin-dashboard/components/SubscribersDonut";
import styles from "./page.module.css";

export default function SubscribersPage() {
  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "analytics", "subscribers"],
    queryFn: fetchSubscribers,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });

  return (
    <section className={styles.page} aria-labelledby="subscribers-page-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="subscribers-page-title" className={styles.title}>
            구독 현황
          </h1>
          <p className={styles.caption}>
            {data ? `기준: ${formatAsOf(data.as_of)} KST` : "현재 시점 기준"}
          </p>
          <p className={styles.caption}>
            도넛/카드/범례 어디든 항목을 누르면 해당 사용자 목록(고객관리)으로 이동합니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          aria-label="구독 현황 새로고침"
          disabled={isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          구독 데이터를 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>구독 데이터를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </section>
      )}
      {data && <SubscribersDonut data={data} />}

      {data && (
        <PendingCancellationsSection
          count={data.pending_cancellation_count}
          items={data.pending_cancellations}
        />
      )}
    </section>
  );
}

function PendingCancellationsSection({
  count,
  items,
}: {
  count: number;
  items: PendingCancellation[];
}) {
  return (
    <section
      className={styles.pendingSection}
      aria-labelledby="pending-cancellations-title"
    >
      <header className={styles.pendingHeader}>
        <h2 id="pending-cancellations-title" className={styles.pendingTitle}>
          유료 종결 예정 리스트
        </h2>
        <span className={styles.pendingBadge}>
          총 {count.toLocaleString()}건
        </span>
      </header>

      {items.length === 0 ? (
        <p className={styles.pendingEmpty} role="status">
          현재 해지 예약된 구독이 없습니다.
        </p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">사용자</th>
                <th scope="col">해지 신청일</th>
                <th scope="col">유료 종료 예정일</th>
                <th scope="col">남은 일수</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={`${row.user_id}-${row.current_period_end}`}>
                  <td>
                    <Link
                      href={`/admin/users/${row.user_id}`}
                      className={styles.userLink}
                      aria-label={`${row.email_masked} 고객 상세 보기`}
                    >
                      {row.email_masked}
                    </Link>
                  </td>
                  <td>{formatKstDate(row.canceled_at)}</td>
                  <td>{formatKstDate(row.current_period_end)}</td>
                  <td>{daysUntil(row.current_period_end)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length < count && (
            <p className={styles.tableFootnote}>
              최근 종료 예정 {items.length.toLocaleString()}건만 표시됩니다.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function formatAsOf(iso: string): string {
  // iso: 2026-04-29T15:30:00+09:00 → 2026-04-29 15:30
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/);
  if (!m) return iso;
  return `${m[1]} ${m[2]}:${m[3]}`;
}

function formatKstDate(iso: string): string {
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : iso;
}

function daysUntil(iso: string): string {
  const target = new Date(iso).getTime();
  const now = Date.now();
  if (Number.isNaN(target)) return "-";
  const diffMs = target - now;
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (days < 0) return "종료";
  if (days === 0) return "오늘";
  return `D-${days}`;
}

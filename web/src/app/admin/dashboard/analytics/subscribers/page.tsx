"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchSubscribers } from "@/features/admin-dashboard/api/analytics";
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

      {data &&
        data.upcoming_renewals.length === 0 &&
        data.pending_cancellation_count === null && (
          <section className={styles.holdNotice} role="note">
            <p className={styles.holdTitle}>유료 종결 예정 리스트</p>
            <p className={styles.holdMessage}>
              유료 종결 예정 리스트는 PG 연동 후 표시됩니다.
            </p>
          </section>
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

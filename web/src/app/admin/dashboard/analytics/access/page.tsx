"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchAccess,
  type AccessUnit,
} from "@/features/admin-dashboard/api/analytics";
import { DashboardChart, type ChartSeries } from "@/features/admin-dashboard/components/DashboardChart";
import styles from "./page.module.css";

const UNITS: { value: AccessUnit; label: string; hint: string }[] = [
  { value: "day", label: "일별", hint: "최근 30일" },
  { value: "week", label: "주별", hint: "최근 12주" },
  { value: "month", label: "월별", hint: "최근 12개월" },
  { value: "year", label: "연도별", hint: "최근 5년" },
];

const SERIES: ChartSeries[] = [
  { key: "visitors", label: "접속자", tone: "brand" },
  { key: "visits", label: "접속횟수", tone: "success" },
];

export default function AccessAnalyticsPage() {
  const [unit, setUnit] = useState<AccessUnit>("day");
  const activeUnit = UNITS.find((u) => u.value === unit) ?? UNITS[0];

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "analytics", "access", { unit }],
    queryFn: () => fetchAccess({ unit }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const chartData = useMemo(
    () =>
      data?.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start, unit),
        visitors: b.visitors,
        visits: b.visits,
      })) ?? [],
    [data, unit],
  );

  return (
    <section className={styles.page} aria-labelledby="access-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="access-title" className={styles.title}>
            접속 통계
          </h1>
          <p className={styles.caption}>
            회원 로그인 1회를 접속 1회로 봅니다. 접속자 수는 고유 회원 수,
            접속횟수는 로그인 누적 횟수입니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          aria-label="접속 통계 새로고침"
          disabled={isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.filters} role="toolbar" aria-label="기간 단위">
        <div className={styles.unitToggle} role="group" aria-label="집계 단위">
          {UNITS.map((u) => (
            <button
              key={u.value}
              type="button"
              className={
                unit === u.value ? styles.unitButtonActive : styles.unitButton
              }
              aria-pressed={unit === u.value}
              onClick={() => setUnit(u.value)}
            >
              {u.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          접속 데이터를 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>접속 데이터를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {data && (
        <>
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>총 접속자 수</p>
              <p className={styles.summaryValue}>
                {data.total_visitors.toLocaleString()}명
              </p>
              <p className={styles.summaryHint}>
                {activeUnit.hint} ({data.from} ~ {data.to}) 동안 로그인한 고유 회원 수
              </p>
            </div>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>총 접속횟수</p>
              <p className={styles.summaryValue}>
                {data.total_visits.toLocaleString()}회
              </p>
              <p className={styles.summaryHint}>
                {activeUnit.hint} 동안 로그인이 일어난 누적 횟수
              </p>
            </div>
          </div>

          <div className={styles.chartBox}>
            <h2 className={styles.chartTitle}>
              {activeUnit.label} 접속 추이
            </h2>
            {chartData.length === 0 ? (
              <p className={styles.statusMessage}>
                해당 구간에 접속 기록이 없습니다.
              </p>
            ) : (
              <DashboardChart
                variant="line"
                data={chartData}
                xKey="bucket_start"
                series={SERIES}
                height={260}
                ariaLabel={`${activeUnit.label} 접속자/접속횟수 추세`}
              />
            )}
          </div>

          <div className={styles.tableBox}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>기간</th>
                  <th>접속자 수</th>
                  <th>접속횟수</th>
                </tr>
              </thead>
              <tbody>
                {data.buckets.length === 0 ? (
                  <tr>
                    <td colSpan={3}>해당 구간에 접속 기록이 없습니다.</td>
                  </tr>
                ) : (
                  [...data.buckets].reverse().map((b) => (
                    <tr key={b.bucket_start}>
                      <td>{formatBucket(b.bucket_start, unit)}</td>
                      <td className={styles.numCell}>
                        {b.visitors.toLocaleString()}명
                      </td>
                      <td className={styles.numCell}>
                        {b.visits.toLocaleString()}회
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function formatBucket(iso: string, unit: AccessUnit): string {
  // iso = YYYY-MM-DD (KST)
  const [y, m, d] = iso.split("-");
  if (unit === "year") return `${y}년`;
  if (unit === "month") return `${y}-${m}`;
  if (unit === "week") return `${m}-${d} 주`;
  return `${m}-${d}`;
}

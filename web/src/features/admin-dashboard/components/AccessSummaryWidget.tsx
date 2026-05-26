"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAccess, type AccessResponse } from "../api/analytics";
import { DashboardChart, type ChartSeries } from "./DashboardChart";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./AccessSummaryWidget.module.css";

export const ACCESS_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "access-summary",
] as const;

const SERIES: ChartSeries[] = [
  { key: "visitors", label: "접속자", tone: "brand" },
  { key: "visits", label: "접속횟수", tone: "success" },
];

export function AccessSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ACCESS_SUMMARY_KEY,
    queryFn: () => fetchAccess({ unit: "day" }),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="접속 통계"
      caption="최근 30일 일별 접속자 수와 접속 횟수를 보여줍니다."
      detailHref="/admin/dashboard/analytics/access"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && data.buckets.length === 0 && (
        <WidgetEmptyState message="접속 기록이 없습니다." />
      )}
      {data && data.buckets.length > 0 && <AccessBody data={data} />}
    </DashboardWidget>
  );
}

function AccessBody({ data }: { data: AccessResponse }) {
  const chartData = useMemo(
    () =>
      data.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start),
        visitors: b.visitors,
        visits: b.visits,
      })),
    [data.buckets],
  );

  const last = data.buckets[data.buckets.length - 1];

  return (
    <div className={styles.body}>
      <DashboardChart
        variant="line"
        data={chartData}
        xKey="bucket_start"
        series={SERIES}
        height={160}
        ariaLabel={`최근 ${data.buckets.length}개 구간 접속 추세 — 누적 접속자 ${data.total_visitors}명`}
      />
      <dl className={styles.figures}>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>구간 접속자</dt>
          <dd className={styles.figureValue}>
            {data.total_visitors.toLocaleString()}명
          </dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>구간 접속횟수</dt>
          <dd className={styles.figureValue}>
            {data.total_visits.toLocaleString()}회
          </dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>최근 일자</dt>
          <dd className={styles.figureValue}>
            {formatBucket(last.bucket_start)} ({last.visitors}명 / {last.visits}회)
          </dd>
        </div>
      </dl>
    </div>
  );
}

function formatBucket(iso: string): string {
  // iso = YYYY-MM-DD
  const [, m, d] = iso.split("-");
  return `${m}-${d}`;
}

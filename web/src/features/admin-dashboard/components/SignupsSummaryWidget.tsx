"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSignups, type SignupsResponse } from "../api/analytics";
import { DashboardChart, type ChartSeries } from "./DashboardChart";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./SignupsSummaryWidget.module.css";

export const SIGNUPS_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "signups-summary",
] as const;

const SERIES: ChartSeries[] = [
  { key: "cumulative", label: "누적", tone: "brand" },
  { key: "active", label: "활성", tone: "success" },
  { key: "new_signups", label: "신규", tone: "warning" },
];

export function SignupsSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: SIGNUPS_SUMMARY_KEY,
    queryFn: () => fetchSignups({ unit: "month" }),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="가입자 추이"
      caption="최근 월별 누적·활성 사용자 추세를 한눈에 확인합니다."
      detailHref="/admin/dashboard/analytics/signups"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && data.buckets.length === 0 && (
        <WidgetEmptyState message="가입자 활동이 없습니다." />
      )}
      {data && data.buckets.length > 0 && <SignupsBody data={data} />}
    </DashboardWidget>
  );
}

function SignupsBody({ data }: { data: SignupsResponse }) {
  const chartData = useMemo(
    () =>
      data.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start),
        cumulative: b.cumulative,
        active: b.active,
        new_signups: b.new_signups,
      })),
    [data.buckets],
  );

  const last = data.buckets[data.buckets.length - 1];

  const ariaLabel = `최근 ${data.buckets.length}개 구간 가입자 추세 — 현재 누적 ${last.cumulative}명, 최근 신규 ${last.new_signups}명`;

  return (
    <div className={styles.body}>
      <DashboardChart
        variant="line"
        data={chartData}
        xKey="bucket_start"
        series={SERIES}
        height={160}
        ariaLabel={ariaLabel}
      />
      <dl className={styles.figures}>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>현재 누적</dt>
          <dd className={styles.figureValue}>
            {last.cumulative.toLocaleString()}명
          </dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>최근 신규</dt>
          <dd className={`${styles.figureValue} ${newToneClass(last.new_signups, styles)}`}>
            {formatNew(last.new_signups)}
          </dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>최근 버킷</dt>
          <dd className={styles.figureValue}>{formatBucket(last.bucket_start)}</dd>
        </div>
      </dl>
    </div>
  );
}

function formatBucket(iso: string): string {
  const [y, m] = iso.split("-");
  return `${y}-${m}`;
}

function formatNew(n: number): string {
  if (n > 0) return `+${n.toLocaleString()}명`;
  return "0명";
}

function newToneClass(n: number, s: Record<string, string>): string {
  return n > 0 ? s.deltaUp : "";
}

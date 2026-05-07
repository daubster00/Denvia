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
      })),
    [data.buckets],
  );

  const last = data.buckets[data.buckets.length - 1];
  const prev =
    data.buckets.length > 1
      ? data.buckets[data.buckets.length - 2]
      : undefined;
  const delta = prev ? last.cumulative - prev.cumulative : null;

  const ariaLabel = `최근 ${data.buckets.length}개 구간 가입자 추세 — 현재 누적 ${last.cumulative}명`;

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
          <dt className={styles.figureLabel}>최근 변화</dt>
          <dd className={`${styles.figureValue} ${deltaToneClass(delta, styles)}`}>
            {formatDelta(delta)}
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

function formatDelta(delta: number | null): string {
  if (delta === null) return "—";
  if (delta > 0) return `+${delta.toLocaleString()}명`;
  if (delta < 0) return `${delta.toLocaleString()}명`;
  return "변동 없음";
}

function deltaToneClass(
  delta: number | null,
  s: Record<string, string>,
): string {
  if (delta === null || delta === 0) return "";
  return delta > 0 ? s.deltaUp : s.deltaDown;
}

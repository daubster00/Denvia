"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSignups } from "../api/analytics";
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

export function SignupsSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: SIGNUPS_SUMMARY_KEY,
    queryFn: () => fetchSignups({ unit: "month" }),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="가입자 추이"
      caption="최근 월별 누적·활성·탈퇴 사용자 수를 요약합니다."
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

function SignupsBody({
  data,
}: {
  data: Awaited<ReturnType<typeof fetchSignups>>;
}) {
  const last = data.buckets[data.buckets.length - 1];
  return (
    <dl className={styles.figures}>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>현재 누적</dt>
        <dd className={styles.figureValue}>
          {last.cumulative.toLocaleString()}명
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>활성</dt>
        <dd className={styles.figureValue}>{last.active.toLocaleString()}명</dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>누적 탈퇴</dt>
        <dd className={styles.figureValue}>
          {last.withdrawn.toLocaleString()}명
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>최근 버킷</dt>
        <dd className={styles.figureValue}>{formatBucket(last.bucket_start)}</dd>
      </div>
    </dl>
  );
}

function formatBucket(iso: string): string {
  const [y, m] = iso.split("-");
  return `${y}-${m}`;
}

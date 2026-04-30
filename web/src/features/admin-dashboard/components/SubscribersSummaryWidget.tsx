"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSubscribers } from "../api/analytics";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./SubscribersSummaryWidget.module.css";

export const SUBSCRIBERS_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "subscribers-summary",
] as const;

export function SubscribersSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: SUBSCRIBERS_SUMMARY_KEY,
    queryFn: fetchSubscribers,
    refetchInterval: 60_000,
  });

  const total = data
    ? data.free_count + data.pro_count + data.blocked_count + data.withdrawn_count
    : 0;

  return (
    <DashboardWidget
      title="구독 현황"
      caption="현재 시점 무료/Pro/차단/탈퇴 사용자 수입니다."
      detailHref="/admin/dashboard/analytics/subscribers"
      footnote="갱신 예정일은 PG 연동 후 표시됩니다"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && total === 0 && (
        <WidgetEmptyState message="현재 구독 사용자가 없습니다." />
      )}
      {data && total > 0 && <SubscribersBody data={data} />}
    </DashboardWidget>
  );
}

function SubscribersBody({
  data,
}: {
  data: Awaited<ReturnType<typeof fetchSubscribers>>;
}) {
  return (
    <dl className={styles.figures}>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>무료</dt>
        <dd className={styles.figureValue}>
          {data.free_count.toLocaleString()}명
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>Pro</dt>
        <dd className={styles.figureValue}>
          {data.pro_count.toLocaleString()}명
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>차단</dt>
        <dd className={styles.figureValue}>
          {data.blocked_count.toLocaleString()}명
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>탈퇴</dt>
        <dd className={styles.figureValue}>
          {data.withdrawn_count.toLocaleString()}명
        </dd>
      </div>
    </dl>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchFeedback } from "../api/analytics";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./FeedbackSummaryWidget.module.css";

export const FEEDBACK_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "feedback-summary",
] as const;

export function FeedbackSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: FEEDBACK_SUMMARY_KEY,
    queryFn: () => fetchFeedback({ unit: "month", per_page: 1 }),
    refetchInterval: 60_000,
  });

  const isEmpty =
    data &&
    data.summary.good_count === 0 &&
    data.summary.bad_count === 0;

  return (
    <DashboardWidget
      title="피드백 비율"
      caption="GOOD/BAD 피드백 분포와 응답 품질 추이입니다."
      tone="ready"
      detailHref="/admin/dashboard/analytics/feedback"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {!isLoading && !error && isEmpty && (
        <WidgetEmptyState message="피드백 데이터가 없습니다." />
      )}
      {data && !isEmpty && <FeedbackBody data={data} />}
    </DashboardWidget>
  );
}

function FeedbackBody({
  data,
}: {
  data: Awaited<ReturnType<typeof fetchFeedback>>;
}) {
  const { good_count, bad_count, good_ratio } = data.summary;
  const pct =
    good_ratio !== null ? `${(good_ratio * 100).toFixed(1)}%` : "—";

  return (
    <dl className={styles.figures}>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>GOOD 건수</dt>
        <dd className={`${styles.figureValue} ${styles.good}`}>
          {good_count.toLocaleString()}건
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>BAD 건수</dt>
        <dd className={`${styles.figureValue} ${styles.bad}`}>
          {bad_count.toLocaleString()}건
        </dd>
      </div>
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>GOOD 비율</dt>
        <dd className={styles.figureValue}>{pct}</dd>
      </div>
    </dl>
  );
}

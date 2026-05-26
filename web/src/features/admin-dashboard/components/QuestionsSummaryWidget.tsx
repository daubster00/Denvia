"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchQuestions, type QuestionsResponse } from "../api/analytics";
import { DashboardChart, type ChartSeries } from "./DashboardChart";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./QuestionsSummaryWidget.module.css";

export const QUESTIONS_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "questions-summary",
] as const;

const SERIES: ChartSeries[] = [
  { key: "count", label: "질문 수", tone: "brand" },
];

export function QuestionsSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: QUESTIONS_SUMMARY_KEY,
    queryFn: () => fetchQuestions({ unit: "day", per_page: 1, page: 1 }),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="질문 통계"
      caption="최근 30일 동안 사용자가 보낸 질문 수입니다."
      detailHref="/admin/dashboard/analytics/questions"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && data.buckets.length === 0 && (
        <WidgetEmptyState message="질문 기록이 없습니다." />
      )}
      {data && data.buckets.length > 0 && <QuestionsBody data={data} />}
    </DashboardWidget>
  );
}

function QuestionsBody({ data }: { data: QuestionsResponse }) {
  const chartData = useMemo(
    () =>
      data.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start),
        count: b.count,
      })),
    [data.buckets],
  );

  const last = data.buckets[data.buckets.length - 1];
  const avgPerDay = data.buckets.length
    ? Math.round(data.total_count / data.buckets.length)
    : 0;

  return (
    <div className={styles.body}>
      <DashboardChart
        variant="line"
        data={chartData}
        xKey="bucket_start"
        series={SERIES}
        height={160}
        ariaLabel={`최근 ${data.buckets.length}일 질문 추세 — 누적 ${data.total_count}건`}
      />
      <dl className={styles.figures}>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>구간 총 질문</dt>
          <dd className={styles.figureValue}>
            {data.total_count.toLocaleString()}건
          </dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>일평균</dt>
          <dd className={styles.figureValue}>{avgPerDay.toLocaleString()}건</dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>최근 일자</dt>
          <dd className={styles.figureValue}>
            {formatBucket(last.bucket_start)} ({last.count}건)
          </dd>
        </div>
      </dl>
    </div>
  );
}

function formatBucket(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${m}-${d}`;
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSegments, type SegmentKey } from "../api/analytics";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./SegmentsSummaryWidget.module.css";

export const SEGMENTS_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "segments-summary",
] as const;

const LABELS: Record<SegmentKey, string> = {
  doctor: "치과의사",
  hygienist: "치과위생사",
  student_other: "학생/기타",
};

export function SegmentsSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: SEGMENTS_SUMMARY_KEY,
    queryFn: () => fetchSegments({}),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="가입유형 분포"
      caption="치과의사·치과위생사·학생/기타 사용자 수를 요약합니다."
      detailHref="/admin/dashboard/analytics/segments"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && data.total === 0 && (
        <WidgetEmptyState message="사용자 데이터가 없습니다." />
      )}
      {data && data.total > 0 && <SegmentsBody data={data} />}
    </DashboardWidget>
  );
}

function SegmentsBody({
  data,
}: {
  data: Awaited<ReturnType<typeof fetchSegments>>;
}) {
  const totalActive = data.by_segment.reduce((s, r) => s + r.count, 0);
  return (
    <dl className={styles.figures}>
      {data.by_segment.map((row) => (
        <div key={row.segment} className={styles.figureItem}>
          <dt className={styles.figureLabel}>{LABELS[row.segment]}</dt>
          <dd className={styles.figureValue}>
            {row.count.toLocaleString()}명
          </dd>
        </div>
      ))}
      <div className={styles.figureItem}>
        <dt className={styles.figureLabel}>합계</dt>
        <dd className={styles.figureValue}>
          {totalActive.toLocaleString()}명
        </dd>
      </div>
    </dl>
  );
}

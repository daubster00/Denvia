"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchAnomalyList,
  type AnomalyEventItem,
} from "@/features/admin-anomaly/api/anomaly";
import { fetchSupportCounts } from "@/features/admin-support/api/inquiries";
import { formatAnomalyType } from "@/features/admin-users/labels";
import {
  DashboardWidget,
  WidgetEmptyState,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./AnomalyCSSummaryWidget.module.css";

export const ANOMALY_CS_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "anomaly-cs-summary",
] as const;

const ANOMALY_QUERY_KEY = [
  ...ANOMALY_CS_SUMMARY_KEY,
  "anomaly-new",
] as const;
const SUPPORT_QUERY_KEY = [
  ...ANOMALY_CS_SUMMARY_KEY,
  "support-counts",
] as const;

const KST_FORMAT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatRecentTime(value: string): string {
  try {
    return KST_FORMAT.format(new Date(value));
  } catch {
    return value;
  }
}

function targetLabel(event: AnomalyEventItem): string {
  return (
    event.target_user_email_masked ??
    (event.ip ? `IP ${event.ip}` : "대상 없음")
  );
}

export function AnomalyCSSummaryWidget() {
  const anomalyQuery = useQuery({
    queryKey: ANOMALY_QUERY_KEY,
    queryFn: () =>
      fetchAnomalyList({ status_in: ["new"], page: 1, per_page: 3 }),
    refetchInterval: 60_000,
  });

  const supportQuery = useQuery({
    queryKey: SUPPORT_QUERY_KEY,
    queryFn: fetchSupportCounts,
    refetchInterval: 60_000,
  });

  const isLoading = anomalyQuery.isLoading || supportQuery.isLoading;
  const hasError = Boolean(anomalyQuery.error || supportQuery.error);

  function handleRetry() {
    if (anomalyQuery.error) anomalyQuery.refetch();
    if (supportQuery.error) supportQuery.refetch();
  }

  const anomalyData = anomalyQuery.data;
  const supportData = supportQuery.data;
  const newAnomalyCount = anomalyData?.total ?? 0;
  const openInquiries = supportData?.open_inquiries ?? 0;
  const recentItems = anomalyData?.items ?? [];
  const totalPending = newAnomalyCount + openInquiries;

  return (
    <DashboardWidget
      title="이상탐지 / CS"
      caption="처리 대기 건과 최근 이상 이벤트를 표시합니다."
      detailHref="/admin/anomaly"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && hasError && <WidgetErrorState onRetry={handleRetry} />}
      {!isLoading && !hasError && (
        <>
          <dl className={styles.figures}>
            <Link
              className={styles.figureLink}
              href="/admin/anomaly"
              aria-label="이상행동 미검토 상세 보기"
            >
              <div className={styles.figureItem}>
                <dt className={styles.figureLabel}>이상행동 미검토</dt>
                <dd
                  className={`${styles.figureValue} ${
                    newAnomalyCount > 0 ? styles.figureAlert : ""
                  }`}
                >
                  {newAnomalyCount.toLocaleString()}건
                </dd>
              </div>
            </Link>
            <Link
              className={styles.figureLink}
              href="/admin/cs"
              aria-label="미응답 문의 상세 보기"
            >
              <div className={styles.figureItem}>
                <dt className={styles.figureLabel}>미응답 문의</dt>
                <dd
                  className={`${styles.figureValue} ${
                    openInquiries > 0 ? styles.figureAlert : ""
                  }`}
                >
                  {openInquiries.toLocaleString()}건
                </dd>
              </div>
            </Link>
          </dl>

          <div className={styles.recentBlock}>
            <p className={styles.recentTitle}>최근 이상행동</p>
            {recentItems.length === 0 ? (
              totalPending === 0 ? (
                <WidgetEmptyState message="처리 대기 건이 없습니다." />
              ) : (
                <p className={styles.recentEmpty}>
                  미검토 이상행동이 없습니다.
                </p>
              )
            ) : (
              <ul className={styles.recentList}>
                {recentItems.map((event) => (
                  <li key={event.id} className={styles.recentItem}>
                    <span className={styles.recentType}>
                      {formatAnomalyType(event.type)}
                    </span>
                    <span className={styles.recentTarget}>
                      {targetLabel(event)}
                    </span>
                    <time
                      className={styles.recentTime}
                      dateTime={event.created_at}
                    >
                      {formatRecentTime(event.created_at)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </DashboardWidget>
  );
}

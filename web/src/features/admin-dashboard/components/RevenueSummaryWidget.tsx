"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchRevenueVariance } from "../api/analytics";
import {
  DashboardWidget,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./RevenueSummaryWidget.module.css";

export const REVENUE_SUMMARY_KEY = [
  "admin",
  "dashboard",
  "revenue-summary",
] as const;

export function RevenueSummaryWidget() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: REVENUE_SUMMARY_KEY,
    queryFn: () => fetchRevenueVariance({}),
    refetchInterval: 60_000,
  });

  return (
    <DashboardWidget
      title="재무 요약"
      caption="당월 매출·토큰 비용·차액·에러 요약입니다."
      tone="ready"
      detailHref="/admin/finance/revenue"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && error && <WidgetErrorState onRetry={() => refetch()} />}
      {data && !error && (
        <dl className={styles.figures}>
          <div className={styles.figureItem}>
            <dt className={styles.figureLabel}>당월 총매출</dt>
            <dd className={styles.figureValue}>
              {data.gross_revenue_krw.toLocaleString("ko-KR")}원
            </dd>
          </div>
          <div className={styles.figureItem}>
            <dt className={styles.figureLabel}>환불액</dt>
            <dd
              className={`${styles.figureValue} ${
                data.refund_krw > 0 ? styles.varianceNegative : ""
              }`}
            >
              {data.refund_krw > 0 ? "−" : ""}
              {data.refund_krw.toLocaleString("ko-KR")}원
            </dd>
          </div>
          <div className={styles.figureItem}>
            <dt className={styles.figureLabel}>순매출</dt>
            <dd className={styles.figureValue}>
              {data.net_revenue_krw.toLocaleString("ko-KR")}원
            </dd>
          </div>
          <div className={styles.figureItem}>
            <dt className={styles.figureLabel}>토큰 비용 (KRW)</dt>
            <dd className={styles.figureValue}>
              {data.token_cost_krw.toLocaleString("ko-KR")}원
            </dd>
          </div>
          <div className={styles.figureItem}>
            <dt className={styles.figureLabel}>차액</dt>
            <dd
              className={`${styles.figureValue} ${
                data.variance_krw < 0
                  ? styles.varianceNegative
                  : styles.variancePositive
              }`}
            >
              {data.variance_krw < 0 ? "−" : ""}
              {Math.abs(data.variance_krw).toLocaleString("ko-KR")}원
            </dd>
          </div>
          <div className={styles.figureItem}>
            <dt className={styles.figureLabel}>에러·이상</dt>
            <dd className={styles.figureValue}>
              {(data.error_count + data.anomaly_count).toLocaleString("ko-KR")}
              건
            </dd>
          </div>
        </dl>
      )}
    </DashboardWidget>
  );
}

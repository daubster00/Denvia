"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { IconDownload } from "@wanteddev/wds-icon";
import {
  fetchRevenueVariance,
  fetchRevenueVarianceExport,
  fetchRevenueVarianceSeries,
} from "@/features/admin-dashboard/api/analytics";
import { DashboardChart } from "@/features/admin-dashboard/components/DashboardChart";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import styles from "./page.module.css";

function currentKstYearMonth(): string {
  const now = new Date();
  const kst = new Date(now.getTime() + (now.getTimezoneOffset() + 540) * 60_000);
  const y = kst.getFullYear();
  const m = String(kst.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

export default function RevenueDashboardPage() {
  const [yearMonth, setYearMonth] = useState<string>(currentKstYearMonth());
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const monthQuery = useQuery({
    queryKey: ["admin", "finance", "revenue-variance", { year_month: yearMonth }],
    queryFn: () => fetchRevenueVariance({ year_month: yearMonth }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const seriesQuery = useQuery({
    queryKey: ["admin", "finance", "revenue-variance-series", { months: 12 }],
    queryFn: () => fetchRevenueVarianceSeries({ months: 12 }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await fetchRevenueVarianceExport({
        year_month: yearMonth,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(
        err instanceof Error ? err.message : "엑셀 다운로드에 실패했습니다.",
      );
    } finally {
      setDownloading(false);
    }
  };

  const data = monthQuery.data;
  const series = seriesQuery.data;

  const isEmpty =
    data &&
    data.gross_revenue_krw === 0 &&
    data.refund_krw === 0 &&
    data.token_cost_krw === 0;
  const errorTotal = data ? data.error_count + data.anomaly_count : 0;

  return (
    <section className={styles.page} aria-labelledby="revenue-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="revenue-title" className={styles.title}>
            매출 대시보드
          </h1>
          <p className={styles.caption}>
            당월 매출과 토큰 비용을 비교하고 차액을 한눈에 확인합니다.
          </p>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={() => {
              monthQuery.refetch();
              seriesQuery.refetch();
            }}
            aria-label="매출 대시보드 새로고침"
            disabled={monthQuery.isFetching}
          >
            ↻ 새로고침
          </button>
        </div>
      </header>

      <div className={styles.controls} role="toolbar" aria-label="기간 선택">
        <label className={styles.monthLabel}>
          <span>조회 월</span>
          <input
            type="month"
            value={yearMonth}
            onChange={(e) => setYearMonth(e.target.value)}
            className={styles.monthInput}
          />
        </label>
        <button
          type="button"
          className={styles.downloadBtn}
          onClick={handleDownload}
          disabled={downloading}
        >
          <IconDownload aria-hidden="true" />
          <span>엑셀 다운로드</span>
        </button>
      </div>

      {downloadError && (
        <p className={styles.downloadError} role="alert">
          {downloadError}
        </p>
      )}

      {monthQuery.isLoading && (
        <p className={styles.statusMessage} role="status">
          매출 데이터를 불러오는 중…
        </p>
      )}

      {!monthQuery.isLoading && monthQuery.error && (
        <section className={styles.errorBox} role="alert">
          <p>매출 데이터를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => monthQuery.refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {data && (
        <>
          <div className={styles.kpiRow}>
            <KPICard
              label="당월 총매출"
              value={`${data.gross_revenue_krw.toLocaleString("ko-KR")}원`}
              trend={{
                direction: "flat",
                text: "환불 차감 전 결제 금액",
              }}
            />
            <KPICard
              label="당월 환불액"
              value={`${data.refund_krw > 0 ? "−" : ""}${data.refund_krw.toLocaleString("ko-KR")}원`}
              trend={
                data.refund_krw > 0
                  ? {
                      direction: "down",
                      text: "총매출에서 차감",
                      tone: "warning",
                    }
                  : {
                      direction: "flat",
                      text: "환불 없음",
                      tone: "success",
                    }
              }
            />
            <KPICard
              label="당월 순매출"
              value={`${data.net_revenue_krw.toLocaleString("ko-KR")}원`}
              trend={{
                direction: "flat",
                text: "총매출 − 환불액",
              }}
            />
            <KPICard
              label="당월 토큰 비용"
              value={`${data.token_cost_krw.toLocaleString("ko-KR")}원`}
              trend={{
                direction: "flat",
                text: `USD ${data.token_cost_usd} · 환율 ₩${data.usd_to_krw.toLocaleString("ko-KR")}/$`,
              }}
            />
            <KPICard
              label="차액 (순매출 − 토큰비용)"
              value={`${data.variance_krw < 0 ? "−" : ""}${Math.abs(data.variance_krw).toLocaleString("ko-KR")}원`}
              trend={
                data.variance_krw < 0
                  ? { direction: "down", text: "적자", tone: "error" }
                  : { direction: "up", text: "흑자", tone: "success" }
              }
            />
            <KPICard
              label="에러·이상로그"
              value={`${errorTotal.toLocaleString("ko-KR")}건`}
              trend={{
                direction: "flat",
                text: `결제 실패 ${data.error_count}건 + 이상 ${data.anomaly_count}건`,
                tone: errorTotal > 0 ? "warning" : "success",
              }}
            />
          </div>

          {isEmpty && (
            <p className={styles.emptyState} role="status">
              선택하신 월에 매출·토큰 데이터가 없습니다.
            </p>
          )}

          {series && (
            <section
              className={styles.chartBlock}
              aria-labelledby="revenue-chart-title"
            >
              <h2 id="revenue-chart-title" className={styles.sectionTitle}>
                월별 12개월 추이
              </h2>
              <DashboardChart
                variant="bar"
                data={series.items.map((item) => ({
                  name: item.year_month,
                  gross_revenue_krw: item.gross_revenue_krw,
                  refund_krw: item.refund_krw,
                  net_revenue_krw: item.net_revenue_krw,
                  token_cost_krw: item.token_cost_krw,
                  variance_krw: item.variance_krw,
                }))}
                series={[
                  {
                    key: "gross_revenue_krw",
                    label: "총매출 (₩)",
                    tone: "brand",
                  },
                  {
                    key: "refund_krw",
                    label: "환불 (₩)",
                    tone: "error",
                  },
                  {
                    key: "net_revenue_krw",
                    label: "순매출 (₩)",
                    tone: "neutral",
                  },
                  {
                    key: "token_cost_krw",
                    label: "토큰 비용 (₩)",
                    tone: "warning",
                  },
                  { key: "variance_krw", label: "차액 (₩)", tone: "success" },
                ]}
                ariaLabel={`총매출·환불·순매출·토큰비용·차액 12개월 추이 — 당월 총매출 ${data.gross_revenue_krw.toLocaleString("ko-KR")}원, 환불 ${data.refund_krw.toLocaleString("ko-KR")}원, 순매출 ${data.net_revenue_krw.toLocaleString("ko-KR")}원, 토큰비용 ${data.token_cost_krw.toLocaleString("ko-KR")}원, 차액 ${data.variance_krw.toLocaleString("ko-KR")}원`}
              />
            </section>
          )}
        </>
      )}
    </section>
  );
}

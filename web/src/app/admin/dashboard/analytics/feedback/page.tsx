"use client";

import { useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  buildFeedbackExportUrl,
  fetchFeedback,
  type FeedbackItem,
} from "@/features/admin-dashboard/api/analytics";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import { DashboardChart } from "@/features/admin-dashboard/components/DashboardChart";
import { FeedbackDetailTable } from "@/features/admin-dashboard/components/FeedbackDetailTable";
import { AnswerDetailDrawer } from "@/features/admin-dashboard/components/AnswerDetailDrawer";
import styles from "./page.module.css";

type Unit = "day" | "week" | "month";
type RatingFilter = "all" | "good" | "bad";

const UNITS: { value: Unit; label: string }[] = [
  { value: "day", label: "일" },
  { value: "week", label: "주" },
  { value: "month", label: "월" },
];

const RATING_FILTERS: { value: RatingFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "good", label: "GOOD만" },
  { value: "bad", label: "BAD만" },
];

const PER_PAGE = 50;

export default function FeedbackPage() {
  const [unit, setUnit] = useState<Unit>("month");
  const [ratingFilter, setRatingFilter] = useState<RatingFilter>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [drawerItem, setDrawerItem] = useState<FeedbackItem | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const qc = useQueryClient();

  const queryKey = [
    "admin",
    "analytics",
    "feedback",
    { unit, from, to, rating_filter: ratingFilter, page, q },
  ] as const;

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey,
    queryFn: () =>
      fetchFeedback({
        unit,
        from: from || undefined,
        to: to || undefined,
        rating_filter: ratingFilter,
        page,
        per_page: PER_PAGE,
        q: q || undefined,
      }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ["admin", "analytics", "feedback"] });
  }

  function handleUnitChange(u: Unit) {
    setUnit(u);
    setPage(1);
  }

  function handleRatingFilterChange(rf: RatingFilter) {
    setRatingFilter(rf);
    setPage(1);
  }

  function handleSearchChange(value: string) {
    setQ(value);
    setPage(1);
  }

  const handleExport = useCallback(() => {
    setIsExporting(true);
    setExportError(null);

    try {
      const url = buildFeedbackExportUrl({
        unit,
        from: from || undefined,
        to: to || undefined,
        rating_filter: ratingFilter,
        q: q || undefined,
      });
      const iframe = document.createElement("iframe");
      iframe.src = url;
      iframe.hidden = true;
      iframe.title = "feedback-export-download";
      document.body.appendChild(iframe);
      window.setTimeout(() => iframe.remove(), 60_000);
    } catch (err) {
      setExportError(
        err instanceof Error
          ? "엑셀 파일을 내려받지 못했습니다. 잠시 후 다시 시도해 주세요."
          : "엑셀 파일을 내려받지 못했습니다."
      );
    } finally {
      window.setTimeout(() => setIsExporting(false), 700);
    }
  }, [unit, from, to, ratingFilter, q]);

  const summary = data?.summary;
  const series = data?.series ?? [];
  const goodPct =
    summary?.good_ratio !== null && summary?.good_ratio !== undefined
      ? `${(summary.good_ratio * 100).toFixed(1)}%`
      : "—";

  return (
    <section className={styles.page} aria-labelledby="feedback-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="feedback-title" className={styles.title}>
            피드백 분석
          </h1>
          <p className={styles.caption}>
            GOOD/BAD 피드백 비율과 응답 품질 추이를 확인합니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={handleRefresh}
          aria-label="피드백 분석 새로고침"
          disabled={isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      {/* 필터 바 */}
      <div className={styles.filters} role="toolbar" aria-label="피드백 필터">
        <div className={styles.toggleGroup}>
          {UNITS.map((u) => (
            <button
              key={u.value}
              type="button"
              className={
                unit === u.value ? styles.toggleBtnActive : styles.toggleBtn
              }
              aria-pressed={unit === u.value}
              onClick={() => handleUnitChange(u.value)}
            >
              {u.label}
            </button>
          ))}
        </div>

        <div className={styles.toggleGroup}>
          {RATING_FILTERS.map((rf) => (
            <button
              key={rf.value}
              type="button"
              className={
                ratingFilter === rf.value
                  ? styles.toggleBtnActive
                  : styles.toggleBtn
              }
              aria-pressed={ratingFilter === rf.value}
              onClick={() => handleRatingFilterChange(rf.value)}
            >
              {rf.label}
            </button>
          ))}
        </div>

        <div className={styles.dateRange}>
          <label className={styles.dateLabel}>
            <span className={styles.dateLabelText}>시작일</span>
            <input
              type="date"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
                setPage(1);
              }}
              className={styles.dateInput}
              aria-label="시작일"
            />
          </label>
          <label className={styles.dateLabel}>
            <span className={styles.dateLabelText}>종료일</span>
            <input
              type="date"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
                setPage(1);
              }}
              className={styles.dateInput}
              aria-label="종료일"
            />
          </label>
        </div>

        <input
          type="search"
          placeholder="질문·답변 키워드 검색"
          value={q}
          onChange={(e) => handleSearchChange(e.target.value)}
          className={styles.searchInput}
          aria-label="질문·답변 키워드 검색"
        />
      </div>

      {/* 로딩 / 에러 */}
      {isLoading && (
        <p className={styles.statusMessage} role="status">
          피드백 데이터를 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>피드백 데이터를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {data && (
        <>
          {/* KPI 행 */}
          <div className={styles.kpiRow}>
            <KPICard
              label="GOOD 건수"
              value={`${summary!.good_count.toLocaleString()}건`}
            />
            <KPICard
              label="BAD 건수"
              value={`${summary!.bad_count.toLocaleString()}건`}
            />
            <p className={styles.ratioText}>GOOD 비율: {goodPct}</p>
          </div>

          {/* 추세 차트 */}
          <div className={styles.chartBox}>
            <DashboardChart
              variant="bar"
              data={series}
              xKey="bucket_start"
              series={[
                { key: "good", label: "GOOD", tone: "success" },
                { key: "bad", label: "BAD", tone: "error" },
              ]}
              height={280}
              ariaLabel={`피드백 추세 — GOOD ${summary!.good_count}건, BAD ${summary!.bad_count}건`}
              emptyMessage="이 기간에 피드백이 없습니다."
            />
          </div>

          {/* 상세 리스트 */}
          <FeedbackDetailTable
            items={data.items}
            total={data.total}
            page={data.page}
            perPage={data.per_page}
            onPageChange={setPage}
            onRowClick={setDrawerItem}
            onExport={handleExport}
            isExporting={isExporting}
            exportError={exportError}
          />
        </>
      )}

      <AnswerDetailDrawer
        item={drawerItem}
        onClose={() => setDrawerItem(null)}
      />
    </section>
  );
}

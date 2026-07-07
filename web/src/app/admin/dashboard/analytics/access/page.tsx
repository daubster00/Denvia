"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchAccess, type AccessUnit } from "@/features/admin-dashboard/api/analytics";
import { DashboardChart, type ChartSeries } from "@/features/admin-dashboard/components/DashboardChart";
import styles from "./page.module.css";

type SelectableUnit = Exclude<AccessUnit, "week">;

const UNITS: { value: SelectableUnit; label: string }[] = [
  { value: "day", label: "일별" },
  { value: "month", label: "월별" },
  { value: "year", label: "연도별" },
];

const SERIES: ChartSeries[] = [
  { key: "visitors", label: "접속자", tone: "brand" },
  { key: "visits", label: "접속횟수", tone: "success" },
];

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function currentYearMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function lastDayOfMonth(yearMonth: string): string {
  const [year, month] = yearMonth.split("-").map(Number);
  const last = new Date(year, month, 0).getDate();
  return `${yearMonth}-${String(last).padStart(2, "0")}`;
}

function dateLabel(value: string): string {
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
}

function resolveRange(unit: SelectableUnit, day: string, month: string, year: string) {
  if (unit === "day") return { from: day, to: day };
  if (unit === "month") return { from: `${month}-01`, to: lastDayOfMonth(month) };
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

export default function AccessAnalyticsPage() {
  const [unit, setUnit] = useState<SelectableUnit>("day");
  const [selectedDay, setSelectedDay] = useState<string>(() => toIsoDate(new Date()));
  const [selectedMonth, setSelectedMonth] = useState<string>(() => currentYearMonth());
  const [selectedYear, setSelectedYear] = useState<string>(() =>
    String(new Date().getFullYear()),
  );

  const activeUnit = UNITS.find((u) => u.value === unit) ?? UNITS[0];
  const range = useMemo(
    () => resolveRange(unit, selectedDay, selectedMonth, selectedYear),
    [selectedDay, selectedMonth, selectedYear, unit],
  );

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "analytics", "access", { unit, ...range }],
    queryFn: () => fetchAccess({ unit, ...range }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  function handleUnitChange(next: SelectableUnit) {
    setUnit(next);
  }

  const chartData = useMemo(
    () =>
      data?.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start, unit),
        visitors: b.visitors,
        visits: b.visits,
      })) ?? [],
    [data, unit],
  );

  return (
    <section className={styles.page} aria-labelledby="access-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="access-title" className={styles.title}>
            접속 통계
          </h1>
          <p className={styles.caption}>
            회원 로그인 1회를 접속 1회로 봅니다. 접속자 수는 고유 회원 수,
            접속횟수는 로그인 누적 횟수입니다. 신규 가입 직후 자동 입장은
            접속에 포함되지 않으며, 재로그인부터 집계됩니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          aria-label="접속 통계 새로고침"
          disabled={isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.filters} role="toolbar" aria-label="기간 단위">
        <div className={styles.unitToggle} role="group" aria-label="집계 단위">
          {UNITS.map((u) => (
            <button
              key={u.value}
              type="button"
              className={
                unit === u.value ? styles.unitButtonActive : styles.unitButton
              }
              aria-pressed={unit === u.value}
              onClick={() => handleUnitChange(u.value)}
            >
              {u.label}
            </button>
          ))}
        </div>
        <div className={styles.dateRange}>
          {unit === "day" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준일</span>
              <input
                type="date"
                value={selectedDay}
                onChange={(e) => setSelectedDay(e.target.value)}
                className={styles.dateInput}
                aria-label="조회 기준일"
              />
              <span className={styles.selectedHint}>{dateLabel(selectedDay)}</span>
            </label>
          ) : null}
          {unit === "month" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준월</span>
              <input
                type="month"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className={styles.dateInput}
                aria-label="조회 기준월"
              />
            </label>
          ) : null}
          {unit === "year" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준연도</span>
              <input
                type="number"
                min="2024"
                max="2099"
                step="1"
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className={styles.dateInput}
                aria-label="조회 기준연도"
              />
            </label>
          ) : null}
        </div>
      </div>

      {isLoading && (
        <p className={styles.statusMessage} role="status">
          접속 데이터를 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>접속 데이터를 불러오지 못했습니다.</p>
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
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>선택 기간 총 접속자 수</p>
              <p className={styles.summaryValue}>
                {data.total_visitors.toLocaleString()}명
              </p>
              <p className={styles.summaryHint}>
                {summaryRangeLabel(unit, data.from, data.to)} 로그인한 고유 회원 수
                (중복 제거)
              </p>
            </div>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>선택 기간 총 접속횟수</p>
              <p className={styles.summaryValue}>
                {data.total_visits.toLocaleString()}회
              </p>
              <p className={styles.summaryHint}>
                {summaryRangeLabel(unit, data.from, data.to)} 누적 로그인 횟수
              </p>
            </div>
          </div>

          <div className={styles.chartBox}>
            <h2 className={styles.chartTitle}>
              {activeUnit.label} 접속 추이
            </h2>
            {chartData.length === 0 ? (
              <p className={styles.statusMessage}>
                해당 구간에 접속 기록이 없습니다.
              </p>
            ) : (
              <DashboardChart
                variant="line"
                data={chartData}
                xKey="bucket_start"
                series={SERIES}
                height={260}
                ariaLabel={`${activeUnit.label} 접속자/접속횟수 추세`}
              />
            )}
          </div>

          <div className={styles.tableBox}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>기간</th>
                  <th>접속자 수</th>
                  <th>접속횟수</th>
                </tr>
              </thead>
              <tbody>
                {data.buckets.length === 0 ? (
                  <tr>
                    <td colSpan={3}>해당 구간에 접속 기록이 없습니다.</td>
                  </tr>
                ) : (
                  [...data.buckets].reverse().map((b) => (
                    <tr key={b.bucket_start}>
                      <td>{formatBucket(b.bucket_start, unit)}</td>
                      <td className={styles.numCell}>
                        {b.visitors.toLocaleString()}명
                      </td>
                      <td className={styles.numCell}>
                        {b.visits.toLocaleString()}회
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function formatBucket(iso: string, unit: AccessUnit): string {
  // iso = YYYY-MM-DD (KST)
  const [y, m, d] = iso.split("-");
  if (unit === "year") return `${y}년`;
  if (unit === "month") return `${y}-${m}`;
  if (unit === "week") return `${m}-${d} 주`;
  return `${m}-${d}`;
}

function summaryRangeLabel(unit: SelectableUnit, from: string, _to: string): string {
  if (unit === "day") return `${dateLabel(from)}에`;
  if (unit === "month") return `${from.slice(0, 7)} 월에`;
  return `${from.slice(0, 4)}년에`;
}

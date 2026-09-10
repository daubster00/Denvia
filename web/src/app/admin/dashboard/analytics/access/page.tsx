"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchAccess, type AccessUnit } from "@/features/admin-dashboard/api/analytics";
import { DashboardChart, type ChartSeries } from "@/features/admin-dashboard/components/DashboardChart";
import styles from "./page.module.css";

// 백엔드가 지원하는 4개 단위를 그대로 노출한다 (주별은 게시판 #144에서 추가).
type SelectableUnit = AccessUnit;

const UNITS: { value: SelectableUnit; label: string }[] = [
  { value: "day", label: "일별" },
  { value: "week", label: "주별" },
  { value: "month", label: "월별" },
  { value: "year", label: "연도별" },
];

// 주별 조회 시 기준일이 속한 주를 포함해 몇 주치를 보여줄지.
const WEEK_SPAN = 12;

const SERIES: ChartSeries[] = [
  { key: "visitors", label: "접속자", tone: "brand" },
  { key: "visits", label: "접속횟수", tone: "success" },
];

// 기기별 그래프(접속횟수 기준). unknown은 값이 있을 때만 덧붙인다.
const DEVICE_SERIES: ChartSeries[] = [
  { key: "pc_visits", label: "PC 접속횟수", tone: "brand" },
  { key: "mobile_visits", label: "모바일 접속횟수", tone: "warning" },
];

const UNKNOWN_SERIES: ChartSeries = {
  key: "unknown_visits",
  label: "구분 불가 접속횟수",
  tone: "neutral",
};

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

/** 주 시작일(일요일)로 내린다 — 백엔드 _truncate_to_unit(unit="week")과 같은 규칙. */
function startOfWeek(d: Date): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  out.setDate(out.getDate() - out.getDay()); // getDay: 일=0 … 토=6
  return out;
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

/** 기준일이 속한 주를 포함해 최근 WEEK_SPAN 주 구간(일요일~토요일)을 만든다. */
function weekRange(baseDay: string): { from: string; to: string } {
  const base = new Date(`${baseDay}T00:00:00`);
  if (Number.isNaN(base.getTime())) return { from: baseDay, to: baseDay };
  const lastStart = startOfWeek(base);
  const end = new Date(lastStart);
  end.setDate(end.getDate() + 6);
  const start = new Date(lastStart);
  start.setDate(start.getDate() - 7 * (WEEK_SPAN - 1));
  return { from: toIsoDate(start), to: toIsoDate(end) };
}

function weekHint(baseDay: string): string {
  const { from, to } = weekRange(baseDay);
  return `${from} ~ ${to} (최근 ${WEEK_SPAN}주)`;
}

function resolveRange(
  unit: SelectableUnit,
  day: string,
  weekBase: string,
  month: string,
  year: string,
) {
  if (unit === "day") return { from: day, to: day };
  if (unit === "week") return weekRange(weekBase);
  if (unit === "month") return { from: `${month}-01`, to: lastDayOfMonth(month) };
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

export default function AccessAnalyticsPage() {
  const [unit, setUnit] = useState<SelectableUnit>("day");
  const [selectedDay, setSelectedDay] = useState<string>(() => toIsoDate(new Date()));
  const [selectedWeekBase, setSelectedWeekBase] = useState<string>(() =>
    toIsoDate(new Date()),
  );
  const [selectedMonth, setSelectedMonth] = useState<string>(() => currentYearMonth());
  const [selectedYear, setSelectedYear] = useState<string>(() =>
    String(new Date().getFullYear()),
  );

  const activeUnit = UNITS.find((u) => u.value === unit) ?? UNITS[0];
  const range = useMemo(
    () => resolveRange(unit, selectedDay, selectedWeekBase, selectedMonth, selectedYear),
    [selectedDay, selectedWeekBase, selectedMonth, selectedYear, unit],
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

  // 판별 불가(unknown)는 실제로 값이 있을 때만 화면에 내보낸다.
  const hasUnknown = (data?.total_unknown_visits ?? 0) > 0;

  const chartData = useMemo(
    () =>
      data?.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start, unit),
        visitors: b.visitors,
        visits: b.visits,
        pc_visits: b.pc_visits,
        mobile_visits: b.mobile_visits,
        unknown_visits: b.unknown_visits,
      })) ?? [],
    [data, unit],
  );

  const deviceSeries = useMemo(
    () => (hasUnknown ? [...DEVICE_SERIES, UNKNOWN_SERIES] : DEVICE_SERIES),
    [hasUnknown],
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
          {unit === "week" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준일이 속한 주까지</span>
              <input
                type="date"
                value={selectedWeekBase}
                onChange={(e) => setSelectedWeekBase(e.target.value)}
                className={styles.dateInput}
                aria-label="주별 조회 기준일"
              />
              <span className={styles.selectedHint}>{weekHint(selectedWeekBase)}</span>
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

          <div className={styles.deviceGrid}>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>PC로 접속</p>
              <p className={styles.summaryValueSm}>
                {data.total_pc_visitors.toLocaleString()}명 /{" "}
                {data.total_pc_visits.toLocaleString()}회
              </p>
              <p className={styles.summaryHint}>
                컴퓨터(노트북 포함)에서 로그인한 고유 회원 수 / 누적 횟수
              </p>
            </div>
            <div className={styles.summaryItem}>
              <p className={styles.summaryLabel}>휴대폰으로 접속</p>
              <p className={styles.summaryValueSm}>
                {data.total_mobile_visitors.toLocaleString()}명 /{" "}
                {data.total_mobile_visits.toLocaleString()}회
              </p>
              <p className={styles.summaryHint}>
                휴대폰·태블릿에서 로그인한 고유 회원 수 / 누적 횟수
              </p>
            </div>
            {hasUnknown ? (
              <div className={styles.summaryItem}>
                <p className={styles.summaryLabel}>기기 구분 불가</p>
                <p className={styles.summaryValueSm}>
                  {data.total_unknown_visitors.toLocaleString()}명 /{" "}
                  {data.total_unknown_visits.toLocaleString()}회
                </p>
                <p className={styles.summaryHint}>
                  브라우저가 기기 정보를 보내지 않아 판단하지 못한 접속
                </p>
              </div>
            ) : null}
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

          <div className={styles.chartBox}>
            <h2 className={styles.chartTitle}>
              {activeUnit.label} PC · 모바일 접속횟수 추이
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
                series={deviceSeries}
                height={260}
                ariaLabel={`${activeUnit.label} PC/모바일 접속횟수 추세`}
              />
            )}
          </div>

          <div className={styles.tableBox}>
            <div className={styles.tableScroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>기간</th>
                    <th>전체 접속자</th>
                    <th>전체 횟수</th>
                    <th>PC 접속자</th>
                    <th>PC 횟수</th>
                    <th>모바일 접속자</th>
                    <th>모바일 횟수</th>
                    {hasUnknown ? <th>구분 불가 접속자</th> : null}
                    {hasUnknown ? <th>구분 불가 횟수</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {data.buckets.length === 0 ? (
                    <tr>
                      <td colSpan={hasUnknown ? 9 : 7}>
                        해당 구간에 접속 기록이 없습니다.
                      </td>
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
                        <td className={styles.numCell}>
                          {b.pc_visitors.toLocaleString()}명
                        </td>
                        <td className={styles.numCell}>
                          {b.pc_visits.toLocaleString()}회
                        </td>
                        <td className={styles.numCell}>
                          {b.mobile_visitors.toLocaleString()}명
                        </td>
                        <td className={styles.numCell}>
                          {b.mobile_visits.toLocaleString()}회
                        </td>
                        {hasUnknown ? (
                          <td className={styles.numCell}>
                            {b.unknown_visitors.toLocaleString()}명
                          </td>
                        ) : null}
                        {hasUnknown ? (
                          <td className={styles.numCell}>
                            {b.unknown_visits.toLocaleString()}회
                          </td>
                        ) : null}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <ul className={styles.notes}>
            <li>
              PC 접속자 수와 모바일 접속자 수를 더한 값은 전체 접속자 수보다 클 수
              있습니다. 한 회원이 PC와 휴대폰 양쪽으로 접속하면 각각 1명으로
              집계되기 때문입니다.
            </li>
            <li>
              기기 구분은 접속한 브라우저가 알려주는 정보로 판단하며, 일부
              태블릿(아이패드 등)은 PC로 분류될 수 있습니다.
            </li>
          </ul>
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
  // 주별은 그 주의 시작일(일요일)을 라벨로 쓴다.
  if (unit === "week") return `${m}-${d} 주`;
  return `${m}-${d}`;
}

function summaryRangeLabel(unit: SelectableUnit, from: string, to: string): string {
  if (unit === "day") return `${dateLabel(from)}에`;
  if (unit === "week") return `${from} ~ ${to} 기간에`;
  if (unit === "month") return `${from.slice(0, 7)} 월에`;
  return `${from.slice(0, 4)}년에`;
}

"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchSignups,
  type SignupsUnit,
} from "@/features/admin-dashboard/api/analytics";
import { SignupsTrendChart } from "@/features/admin-dashboard/components/SignupsTrendChart";
import styles from "./page.module.css";

type SelectableUnit = Exclude<SignupsUnit, "week">;

const UNITS: { value: SelectableUnit; label: string }[] = [
  { value: "day", label: "일" },
  { value: "month", label: "월" },
  { value: "year", label: "연" },
];

function toISODate(d: Date): string {
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

interface ResolvedQuery {
  /** 실제로 API 에 보낼 집계 단위(차트를 그리는 데이터 granularity). */
  fetchUnit: SignupsUnit;
  from: string;
  to: string;
}

/**
 * "사용자가 고른 단위(unit)"와 "실제로 조회·렌더할 데이터 단위(fetchUnit)"를 분리한다.
 * 월을 고르면 그 달 전체를 '일(day)' 버킷으로 받아 일자별 추이를 그리고,
 * 합산값은 프론트에서 집계한다(#122).
 */
function resolveQuery(
  unit: SelectableUnit,
  day: string,
  month: string,
  year: string,
): ResolvedQuery {
  if (unit === "day") return { fetchUnit: "day", from: day, to: day };
  if (unit === "month")
    return { fetchUnit: "day", from: `${month}-01`, to: lastDayOfMonth(month) };
  return { fetchUnit: "year", from: `${year}-01-01`, to: `${year}-12-31` };
}

export default function SignupsPage() {
  const [unit, setUnit] = useState<SelectableUnit>("day");
  const [selectedDay, setSelectedDay] = useState<string>(() => toISODate(new Date()));
  const [selectedMonth, setSelectedMonth] = useState<string>(() => currentYearMonth());
  const [selectedYear, setSelectedYear] = useState<string>(() =>
    String(new Date().getFullYear()),
  );
  const query = useMemo(
    () => resolveQuery(unit, selectedDay, selectedMonth, selectedYear),
    [selectedDay, selectedMonth, selectedYear, unit],
  );

  function handleUnitChange(next: SelectableUnit) {
    setUnit(next);
  }

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    // fetchUnit + from/to 가 실제 요청을 유일하게 식별한다.
    // (일 단일일 vs 월의 일자 범위는 from/to 로 이미 구분됨)
    queryKey: [
      "admin",
      "analytics",
      "signups",
      { unit: query.fetchUnit, from: query.from, to: query.to },
    ],
    queryFn: () =>
      fetchSignups({
        unit: query.fetchUnit,
        from: query.from,
        to: query.to,
      }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  return (
    <section className={styles.page} aria-labelledby="signups-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 id="signups-title" className={styles.title}>
            가입자 추세
          </h1>
          <p className={styles.caption}>
            신규 가입·탈퇴·활성 사용자 흐름을 시간 단위별로 확인합니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          aria-label="가입자 추세 새로고침"
          disabled={isFetching}
        >
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.filters} role="toolbar" aria-label="기간 필터">
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
          가입자 데이터를 불러오는 중…
        </p>
      )}
      {!isLoading && error && (
        <section className={styles.errorBox} role="alert">
          <p>가입자 데이터를 불러오지 못했습니다.</p>
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
        <SignupsTrendChart
          data={data}
          monthSummary={unit === "month" ? { yearMonth: selectedMonth } : null}
        />
      )}
    </section>
  );
}

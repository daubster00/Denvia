"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnomalyTabs } from "@/features/admin-anomaly/components/AnomalyTabs";
import { AnomalyTable } from "@/features/admin-anomaly/components/AnomalyTable";
import { AnomalyDetailDrawer } from "@/features/admin-anomaly/components/AnomalyDetailDrawer";
import { useAnomalyList } from "@/features/admin-anomaly/hooks/useAnomalyList";
import type {
  AnomalyEventItem,
  AnomalyStatus,
  AnomalyType,
} from "@/features/admin-anomaly/api/anomaly";
import styles from "./page.module.css";

const PER_PAGE = 20;

const STATUS_OPTIONS: { label: string; value: AnomalyStatus[] }[] = [
  // 자동제한/차단 해제 처리 후에도 이력은 사라지지 않게 — 'unblocked' 포함.
  { label: "전체", value: ["new", "reviewed", "actioned", "unblocked"] },
  { label: "미검토", value: ["new"] },
  { label: "검토완료", value: ["reviewed"] },
  { label: "처리됨", value: ["actioned"] },
];

const VALID_TYPES: AnomalyType[] = [
  "login_brute_force",
  "concurrent_ip_login",
  "repeated_question",
  "recovery_abuse",
  "rapid_followup_questions",
];

const VALID_STATUSES: AnomalyStatus[] = ["new", "reviewed", "actioned"];

type PeriodUnit = "all" | "day" | "month" | "year";

const PERIOD_OPTIONS: { value: PeriodUnit; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "day", label: "일별" },
  { value: "month", label: "월별" },
  { value: "year", label: "연도별" },
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

/**
 * 단위와 선택값을 KST 기준 ISO datetime 범위(+09:00)로 변환.
 * 백엔드 created_at 은 TIMESTAMP WITH TIME ZONE 이므로 offset 포함이 안전.
 */
function resolveRange(
  unit: PeriodUnit,
  day: string,
  month: string,
  year: string,
): { from?: string; to?: string } {
  if (unit === "all") return {};
  if (unit === "day") {
    return { from: `${day}T00:00:00+09:00`, to: `${day}T23:59:59+09:00` };
  }
  if (unit === "month") {
    return {
      from: `${month}-01T00:00:00+09:00`,
      to: `${lastDayOfMonth(month)}T23:59:59+09:00`,
    };
  }
  return {
    from: `${year}-01-01T00:00:00+09:00`,
    to: `${year}-12-31T23:59:59+09:00`,
  };
}

export default function AnomalyPage() {
  const searchParams = useSearchParams();
  const initialType = (() => {
    const raw = searchParams.get("type");
    return raw && (VALID_TYPES as string[]).includes(raw)
      ? (raw as AnomalyType)
      : null;
  })();
  const initialStatus = (() => {
    const raw = searchParams.get("status");
    if (raw && (VALID_STATUSES as string[]).includes(raw)) {
      return [raw as AnomalyStatus];
    }
    return ["new", "reviewed", "actioned", "unblocked"] as AnomalyStatus[];
  })();

  const [activeType, setActiveType] = useState<AnomalyType | null>(initialType);
  const [statusIn, setStatusIn] = useState<AnomalyStatus[]>(initialStatus);
  const [page, setPage] = useState(1);
  const [openedAnomalyId, setOpenedAnomalyId] = useState<number | null>(null);

  const [periodUnit, setPeriodUnit] = useState<PeriodUnit>("all");
  const [selectedDay, setSelectedDay] = useState<string>(() =>
    toIsoDate(new Date()),
  );
  const [selectedMonth, setSelectedMonth] = useState<string>(() =>
    currentYearMonth(),
  );
  const [selectedYear, setSelectedYear] = useState<string>(() =>
    String(new Date().getFullYear()),
  );

  const range = useMemo(
    () => resolveRange(periodUnit, selectedDay, selectedMonth, selectedYear),
    [periodUnit, selectedDay, selectedMonth, selectedYear],
  );

  const { data, isLoading, isError, refetch } = useAnomalyList({
    type_in: activeType ? [activeType] : undefined,
    status_in: statusIn,
    from: range.from,
    to: range.to,
    page,
    per_page: PER_PAGE,
  });

  function handleTypeChange(next: AnomalyType | null) {
    setActiveType(next);
    setPage(1);
  }

  function handleStatusChange(next: AnomalyStatus[]) {
    setStatusIn(next);
    setPage(1);
  }

  function handlePeriodChange(next: PeriodUnit) {
    setPeriodUnit(next);
    setPage(1);
  }

  function handleShowDetail(anomaly: AnomalyEventItem) {
    setOpenedAnomalyId(anomaly.id);
  }

  const isStatusActive = (opt: AnomalyStatus[]) =>
    opt.length === statusIn.length && opt.every((s) => statusIn.includes(s));

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>이상탐지</h1>
        <p className={styles.caption}>
          비정상적인 사용 패턴과 보안 이벤트를 모니터링합니다.
        </p>
      </header>

      <AnomalyTabs activeType={activeType} onChange={handleTypeChange} />

      <div className={styles.periodBar} role="toolbar" aria-label="기간 필터">
        <div
          className={styles.unitToggle}
          role="group"
          aria-label="집계 단위"
        >
          {PERIOD_OPTIONS.map((p) => (
            <button
              key={p.value}
              type="button"
              className={
                periodUnit === p.value
                  ? styles.unitButtonActive
                  : styles.unitButton
              }
              aria-pressed={periodUnit === p.value}
              onClick={() => handlePeriodChange(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className={styles.dateRange}>
          {periodUnit === "day" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준일</span>
              <input
                type="date"
                value={selectedDay}
                onChange={(e) => {
                  setSelectedDay(e.target.value);
                  setPage(1);
                }}
                className={styles.dateInput}
                aria-label="조회 기준일"
              />
            </label>
          ) : null}
          {periodUnit === "month" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준월</span>
              <input
                type="month"
                value={selectedMonth}
                onChange={(e) => {
                  setSelectedMonth(e.target.value);
                  setPage(1);
                }}
                className={styles.dateInput}
                aria-label="조회 기준월"
              />
            </label>
          ) : null}
          {periodUnit === "year" ? (
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>기준연도</span>
              <input
                type="number"
                min="2024"
                max="2099"
                step="1"
                value={selectedYear}
                onChange={(e) => {
                  setSelectedYear(e.target.value);
                  setPage(1);
                }}
                className={styles.dateInput}
                aria-label="조회 기준연도"
              />
            </label>
          ) : null}
        </div>
      </div>

      <div className={styles.controls}>
        <div
          className={styles.statusFilter}
          role="group"
          aria-label="상태 필터"
        >
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value.join(",")}
              type="button"
              className={
                isStatusActive(opt.value)
                  ? styles.statusBtnActive
                  : styles.statusBtn
              }
              onClick={() => handleStatusChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={styles.refreshButton}
          onClick={() => refetch()}
          disabled={isLoading}
        >
          새로고침
        </button>
      </div>

      <AnomalyTable
        data={data}
        isLoading={isLoading}
        isError={isError}
        page={page}
        perPage={PER_PAGE}
        onPageChange={setPage}
        onShowDetail={handleShowDetail}
        onRetry={() => refetch()}
      />

      {openedAnomalyId !== null ? (
        <AnomalyDetailDrawer
          anomalyId={openedAnomalyId}
          onClose={() => setOpenedAnomalyId(null)}
        />
      ) : null}
    </section>
  );
}

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchUserTokens } from "@/features/admin-dashboard/api/analytics";
import { UserTokensTable } from "@/features/admin-dashboard/components/UserTokensTable";
import styles from "./page.module.css";

type RangeType = "day" | "month" | "year";
const TOP_N = 5;

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function currentYearMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function currentYear(): string {
  return String(new Date().getFullYear());
}

export default function TokenBreakdownPage() {
  const [range, setRange] = useState<RangeType>("month");
  const [day, setDay] = useState(todayIso());
  const [yearMonth, setYearMonth] = useState(currentYearMonth());
  const [year, setYear] = useState(currentYear());

  const params = {
    range,
    ...(range === "day" ? { from: day, to: day } : {}),
    ...(range === "month" ? { year_month: yearMonth } : {}),
    ...(range === "year" ? { from: `${year}-01-01`, to: `${year}-12-31` } : {}),
    page: 1,
    per_page: TOP_N,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "user-tokens", params],
    queryFn: () => fetchUserTokens(params),
  });

  function handleRangeChange(next: RangeType) {
    setRange(next);
  }

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 className={styles.title}>사용자별 토큰 사용</h1>
          <p className={styles.caption}>
            선택한 기간에서 비용이 가장 높은 사용자 TOP 5만 표시합니다.
          </p>
        </div>
      </header>

      <div className={styles.filters}>
        <div className={styles.rangeToggle}>
          {(["day", "month", "year"] as RangeType[]).map((r) => (
            <button
              key={r}
              className={`${styles.rangeBtn} ${range === r ? styles.rangeBtnActive : ""}`}
              onClick={() => handleRangeChange(r)}
            >
              {r === "day" ? "일" : r === "month" ? "월" : "연"}
            </button>
          ))}
        </div>

        {range === "day" && (
          <input
            type="date"
            className={styles.monthPicker}
            value={day}
            onChange={(e) => setDay(e.target.value)}
            aria-label="기준 날짜"
          />
        )}

        {range === "month" && (
          <input
            type="month"
            className={styles.monthPicker}
            value={yearMonth}
            onChange={(e) => setYearMonth(e.target.value)}
            aria-label="기준 월"
          />
        )}

        {range === "year" && (
          <input
            type="number"
            className={styles.monthPicker}
            value={year}
            min="2024"
            max="2099"
            step="1"
            onChange={(e) => setYear(e.target.value)}
            aria-label="기준 연도"
          />
        )}
      </div>

      {isLoading && <p className={styles.loading}>로딩 중…</p>}

      {error && (
        <p className={styles.errorMsg}>데이터를 불러오지 못했습니다.</p>
      )}

      {data && (
        <UserTokensTable
          items={data.items}
          page={1}
          perPage={TOP_N}
          total={Math.min(data.total, TOP_N)}
          onPageChange={() => undefined}
        />
      )}
    </section>
  );
}

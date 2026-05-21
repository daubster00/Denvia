"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchUserTokens } from "@/features/admin-dashboard/api/analytics";
import { UserTokensTable } from "@/features/admin-dashboard/components/UserTokensTable";
import styles from "./page.module.css";

type RangeType = "day" | "month" | "year";
const PER_PAGE_OPTIONS = [20, 50, 100];

function currentYearMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export default function TokenBreakdownPage() {
  const [range, setRange] = useState<RangeType>("month");
  const [yearMonth, setYearMonth] = useState(currentYearMonth());
  const [perPage, setPerPage] = useState(50);
  const [page, setPage] = useState(1);

  const params = {
    range,
    ...(range === "month" ? { year_month: yearMonth } : {}),
    page,
    per_page: perPage,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "user-tokens", params],
    queryFn: () => fetchUserTokens(params),
  });

  function handleRangeChange(next: RangeType) {
    setRange(next);
    setPage(1);
  }

  function handlePageChange(next: number) {
    setPage(next);
  }

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <Link href="/admin" className={styles.backLink}>
            ← 대시보드 홈으로
          </Link>
          <h1 className={styles.title}>사용자별 토큰 사용</h1>
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

        {range === "month" && (
          <input
            type="month"
            className={styles.monthPicker}
            value={yearMonth}
            onChange={(e) => {
              setYearMonth(e.target.value);
              setPage(1);
            }}
          />
        )}

        <select
          className={styles.perPageSelect}
          value={perPage}
          onChange={(e) => {
            setPerPage(Number(e.target.value));
            setPage(1);
          }}
        >
          {PER_PAGE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}건
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className={styles.loading}>로딩 중…</p>}

      {error && (
        <p className={styles.errorMsg}>데이터를 불러오지 못했습니다.</p>
      )}

      {data && (
        <UserTokensTable
          items={data.items}
          page={data.page}
          perPage={data.per_page}
          total={data.total}
          onPageChange={handlePageChange}
        />
      )}
    </section>
  );
}

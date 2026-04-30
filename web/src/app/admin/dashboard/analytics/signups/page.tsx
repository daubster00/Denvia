"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  fetchSignups,
  type SignupsUnit,
} from "@/features/admin-dashboard/api/analytics";
import { SignupsTrendChart } from "@/features/admin-dashboard/components/SignupsTrendChart";
import styles from "./page.module.css";

const UNITS: { value: SignupsUnit; label: string }[] = [
  { value: "day", label: "일" },
  { value: "week", label: "주" },
  { value: "month", label: "월" },
  { value: "year", label: "연" },
];

export default function SignupsPage() {
  const [unit, setUnit] = useState<SignupsUnit>("month");
  const [from, setFrom] = useState<string>("");
  const [to, setTo] = useState<string>("");

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "analytics", "signups", { unit, from, to }],
    queryFn: () =>
      fetchSignups({
        unit,
        from: from || undefined,
        to: to || undefined,
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
        <div className={styles.unitToggle}>
          {UNITS.map((u) => (
            <button
              key={u.value}
              type="button"
              className={
                unit === u.value ? styles.unitButtonActive : styles.unitButton
              }
              aria-pressed={unit === u.value}
              onClick={() => setUnit(u.value)}
            >
              {u.label}
            </button>
          ))}
        </div>
        <div className={styles.dateRange}>
          <label className={styles.dateLabel}>
            <span className={styles.dateLabelText}>시작일</span>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className={styles.dateInput}
              aria-label="시작일"
            />
          </label>
          <label className={styles.dateLabel}>
            <span className={styles.dateLabelText}>종료일</span>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className={styles.dateInput}
              aria-label="종료일"
            />
          </label>
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
      {data && <SignupsTrendChart data={data} />}
    </section>
  );
}

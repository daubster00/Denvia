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

const UNITS: { value: SignupsUnit; label: string }[] = [
  { value: "day", label: "일" },
  { value: "week", label: "주" },
  { value: "month", label: "월" },
  { value: "year", label: "연" },
];

type RangePreset = "7d" | "30d" | "90d" | "custom";

const RANGE_PRESETS: { value: RangePreset; label: string }[] = [
  { value: "7d", label: "최근 7일" },
  { value: "30d", label: "최근 30일" },
  { value: "90d", label: "최근 90일" },
  { value: "custom", label: "사용자 지정" },
];

function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function computePresetRange(preset: Exclude<RangePreset, "custom">): {
  from: string;
  to: string;
} {
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  const today = new Date();
  const fromDate = new Date(today);
  fromDate.setDate(fromDate.getDate() - (days - 1));
  return { from: toISODate(fromDate), to: toISODate(today) };
}

export default function SignupsPage() {
  const [unit, setUnit] = useState<SignupsUnit>("day");
  const [preset, setPreset] = useState<RangePreset>("7d");
  const [customFrom, setCustomFrom] = useState<string>("");
  const [customTo, setCustomTo] = useState<string>("");

  const { from, to } = useMemo(() => {
    if (preset === "custom") {
      return { from: customFrom || undefined, to: customTo || undefined };
    }
    const range = computePresetRange(preset);
    return { from: range.from, to: range.to };
  }, [preset, customFrom, customTo]);

  const handlePresetChange = (next: RangePreset) => {
    if (next === "custom" && preset !== "custom") {
      const current =
        preset === "custom" ? null : computePresetRange(preset);
      if (current) {
        setCustomFrom(current.from);
        setCustomTo(current.to);
      }
    }
    setPreset(next);
  };

  const { data, error, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "analytics", "signups", { unit, from, to }],
    queryFn: () =>
      fetchSignups({
        unit,
        from,
        to,
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
        <div
          className={styles.presetToggle}
          role="group"
          aria-label="기간 프리셋"
        >
          {RANGE_PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              className={
                preset === p.value
                  ? styles.presetButtonActive
                  : styles.presetButton
              }
              aria-pressed={preset === p.value}
              onClick={() => handlePresetChange(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className={styles.unitToggle} role="group" aria-label="집계 단위">
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
        {preset === "custom" && (
          <div className={styles.dateRange}>
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>시작일</span>
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className={styles.dateInput}
                aria-label="시작일"
              />
            </label>
            <label className={styles.dateLabel}>
              <span className={styles.dateLabelText}>종료일</span>
              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className={styles.dateInput}
                aria-label="종료일"
              />
            </label>
          </div>
        )}
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

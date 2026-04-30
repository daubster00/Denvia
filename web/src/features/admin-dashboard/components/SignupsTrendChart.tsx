"use client";

import { useMemo } from "react";
import { DashboardChart, type ChartSeries } from "./DashboardChart";
import { KPICard } from "./KPICard";
import type {
  SignupsBucket,
  SignupsResponse,
  SignupsUnit,
} from "../api/analytics";
import styles from "./SignupsTrendChart.module.css";

const SERIES: ChartSeries[] = [
  { key: "cumulative", label: "누적", tone: "brand" },
  { key: "active", label: "활성", tone: "success" },
  { key: "withdrawn", label: "탈퇴", tone: "warning" },
];

interface Props {
  data: SignupsResponse;
}

export function SignupsTrendChart({ data }: Props) {
  const chartData = useMemo(
    () =>
      data.buckets.map((b) => ({
        bucket_start: formatBucket(b.bucket_start, data.unit),
        cumulative: b.cumulative,
        active: b.active,
        withdrawn: b.withdrawn,
      })),
    [data.buckets, data.unit],
  );

  const last: SignupsBucket | undefined = data.buckets[data.buckets.length - 1];
  const isEmpty =
    data.buckets.length === 0 ||
    data.buckets.every(
      (b) => b.cumulative === 0 && b.active === 0 && b.withdrawn === 0,
    );

  const ariaLabel = last
    ? `가입자 추세 — 누적 ${last.cumulative}, 활성 ${last.active}, 탈퇴 ${last.withdrawn}`
    : "가입자 추세 — 데이터 없음";

  return (
    <section className={styles.wrapper} aria-labelledby="signups-trend-title">
      <h2 id="signups-trend-title" className={styles.srOnly}>
        가입자 추세 차트
      </h2>
      {isEmpty ? (
        <p className={styles.emptyState} role="status">
          이 기간에 가입자 활동이 없습니다.
        </p>
      ) : (
        <DashboardChart
          variant="line"
          data={chartData}
          xKey="bucket_start"
          series={SERIES}
          height={320}
          ariaLabel={ariaLabel}
          emptyMessage="이 기간에 가입자 활동이 없습니다."
        />
      )}
      <div className={styles.kpiRow}>
        <KPICard label="현재 누적 가입자" value={fmt(last?.cumulative)} />
        <KPICard label="현재 활성" value={fmt(last?.active)} />
        <KPICard label="누적 탈퇴" value={fmt(last?.withdrawn)} />
      </div>
    </section>
  );
}

function fmt(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  return `${n.toLocaleString()}명`;
}

function formatBucket(iso: string, unit: SignupsUnit): string {
  const [y, m, d] = iso.split("-");
  if (unit === "year") return y;
  if (unit === "month") return `${y}-${m}`;
  return `${m}/${d}`;
}

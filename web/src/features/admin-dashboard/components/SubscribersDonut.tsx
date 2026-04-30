"use client";

import { useMemo } from "react";
import { DashboardChart, type ChartSeries } from "./DashboardChart";
import { KPICard } from "./KPICard";
import type { SubscribersResponse } from "../api/analytics";
import styles from "./SubscribersDonut.module.css";

interface Props {
  data: SubscribersResponse;
}

const SEGMENT_LABELS = {
  free: "무료",
  pro: "Pro",
  blocked: "차단",
  withdrawn: "탈퇴",
} as const;

// DashboardChart donut variant: series[0].key가 데이터 dataKey로 쓰이고,
// 각 segment 색은 series[idx % series.length].tone에서 가져온다.
// segment별 tone을 다르게 주려면 4개 series가 필요하지만 react key 충돌을 피하려고
// 의미상 같은 dataKey "value"를 첫 series에만 쓰고 나머지는 sentinel key를 쓴다.
const SERIES: ChartSeries[] = [
  { key: "value", label: SEGMENT_LABELS.free, tone: "success" },
  { key: "segment-pro", label: SEGMENT_LABELS.pro, tone: "brand" },
  { key: "segment-blocked", label: SEGMENT_LABELS.blocked, tone: "error" },
  { key: "segment-withdrawn", label: SEGMENT_LABELS.withdrawn, tone: "neutral" },
];

export function SubscribersDonut({ data }: Props) {
  const segments = useMemo(
    () => [
      { name: SEGMENT_LABELS.free, value: data.free_count },
      { name: SEGMENT_LABELS.pro, value: data.pro_count },
      { name: SEGMENT_LABELS.blocked, value: data.blocked_count },
      { name: SEGMENT_LABELS.withdrawn, value: data.withdrawn_count },
    ],
    [data],
  );

  const total = segments.reduce((acc, s) => acc + s.value, 0);
  const isEmpty = total === 0;

  const ariaLabel = `구독 현황 — 무료 ${data.free_count}명, Pro ${data.pro_count}명, 차단 ${data.blocked_count}명, 탈퇴 ${data.withdrawn_count}명`;

  return (
    <section className={styles.wrapper} aria-labelledby="subscribers-title">
      <h2 id="subscribers-title" className={styles.srOnly}>
        구독 현황 도넛 차트
      </h2>
      {isEmpty ? (
        <p className={styles.emptyState} role="status">
          현재 구독 데이터가 없습니다.
        </p>
      ) : (
        <DashboardChart
          variant="donut"
          data={segments}
          xKey="name"
          series={SERIES}
          height={280}
          ariaLabel={ariaLabel}
        />
      )}

      <ul className={styles.legendList}>
        {segments.map((seg, idx) => {
          const pct = total > 0 ? Math.round((seg.value / total) * 1000) / 10 : 0;
          return (
            <li key={seg.name} className={styles.legendItem}>
              <span
                className={`${styles.swatch} ${styles[`tone${idx}`]}`}
                aria-hidden="true"
              />
              <span className={styles.legendLabel}>{seg.name}</span>
              <span className={styles.legendCount}>
                {seg.value.toLocaleString()}명 ({pct}%)
              </span>
            </li>
          );
        })}
      </ul>

      <div className={styles.kpiRow}>
        <KPICard label="무료" value={fmt(data.free_count)} />
        <KPICard label="Pro" value={fmt(data.pro_count)} />
        <KPICard label="차단" value={fmt(data.blocked_count)} />
        <KPICard label="탈퇴" value={fmt(data.withdrawn_count)} />
      </div>
    </section>
  );
}

function fmt(n: number): string {
  return `${n.toLocaleString()}명`;
}

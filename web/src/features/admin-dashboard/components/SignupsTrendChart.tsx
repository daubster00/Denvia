"use client";

import { useMemo } from "react";
import Link from "next/link";
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
  { key: "new_signups", label: "신규", tone: "warning" },
  { key: "withdrawn", label: "탈퇴", tone: "error" },
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
        new_signups: b.new_signups,
      })),
    [data.buckets, data.unit],
  );

  const last: SignupsBucket | undefined = data.buckets[data.buckets.length - 1];
  const isEmpty =
    data.buckets.length === 0 ||
    data.buckets.every(
      (b) =>
        b.cumulative === 0 &&
        b.active === 0 &&
        b.withdrawn === 0 &&
        b.new_signups === 0,
    );

  const ariaLabel = last
    ? `가입자 추세 — 누적 ${last.cumulative}, 활성 ${last.active}, 신규 ${last.new_signups}, 탈퇴 ${last.withdrawn}`
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
        <Link
          href="/admin/users"
          className={styles.kpiLink}
          aria-label={`전체 가입자 ${fmt(last?.cumulative)} — 고객관리에서 보기`}
        >
          <KPICard label="현재 누적 가입자" value={fmt(last?.cumulative)} />
        </Link>
        <Link
          href="/admin/users?withdrawn=false"
          className={styles.kpiLink}
          aria-label={`활성 사용자 ${fmt(last?.active)} — 고객관리에서 보기`}
        >
          <KPICard label="현재 활성" value={fmt(last?.active)} />
        </Link>
        <Link
          href={newSignupsHref(data)}
          className={styles.kpiLink}
          aria-label={`최근 버킷 신규 ${fmt(last?.new_signups)} — 고객관리에서 보기`}
        >
          <KPICard label="최근 버킷 신규" value={fmt(last?.new_signups)} />
        </Link>
        <Link
          href="/admin/users?withdrawn=true"
          className={styles.kpiLink}
          aria-label={`누적 탈퇴 ${fmt(last?.withdrawn)} — 고객관리에서 보기`}
        >
          <KPICard label="누적 탈퇴" value={fmt(last?.withdrawn)} />
        </Link>
      </div>
    </section>
  );
}

/** 마지막 버킷의 시작~다음 버킷 시작 직전 범위로 created_from/to 필터링. */
function newSignupsHref(data: SignupsResponse): string {
  const last = data.buckets[data.buckets.length - 1];
  if (!last) return "/admin/users";
  const from = last.bucket_start;
  const to = bucketEndDate(last.bucket_start, data.unit);
  return `/admin/users?created_from=${from}&created_to=${to}&withdrawn=false`;
}

function bucketEndDate(iso: string, unit: SignupsUnit): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (unit === "year") return `${y}-12-31`;
  if (unit === "month") {
    const last = new Date(y, m, 0).getDate();
    return `${y}-${String(m).padStart(2, "0")}-${String(last).padStart(2, "0")}`;
  }
  // day / week — 그 날 단일
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
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

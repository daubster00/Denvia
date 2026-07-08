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

interface MonthSummaryContext {
  /** YYYY-MM — 현재 보고 있는 달. 이 값이 있으면 일자별 버킷을 그 달의 요약과 함께 렌더. */
  yearMonth: string;
}

interface Props {
  data: SignupsResponse;
  /**
   * 월 모드일 때 전달. data.buckets 는 그 달의 '일자별' 버킷이고,
   * 이 컨텍스트가 있으면 그 달 합산값(신규 합계·월말 스냅샷)을 요약으로 표기한다(#122).
   */
  monthSummary?: MonthSummaryContext | null;
}

export function SignupsTrendChart({ data, monthSummary }: Props) {
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

  // 월 모드: 그 달 일자별 버킷을 합산해 '이 달 신규 합계'를 구한다.
  // new_signups 는 버킷별 순증(delta)이므로 단순 합이 그 달 신규 총합과 정확히 일치.
  // 누적/활성/탈퇴는 월말 스냅샷(마지막 버킷) 값을 그대로 사용한다.
  const monthNewSum = monthSummary
    ? data.buckets.reduce((sum, b) => sum + b.new_signups, 0)
    : 0;
  const monthLabel = monthSummary ? monthTitle(monthSummary.yearMonth) : "";

  return (
    <section className={styles.wrapper} aria-labelledby="signups-trend-title">
      <h2 id="signups-trend-title" className={styles.srOnly}>
        가입자 추세 차트
      </h2>
      {monthSummary && (
        <p className={styles.summaryCaption}>
          <span className={styles.summaryMonth}>{monthLabel}</span> 일자별 신규
          가입 추이 · 이 달 신규 합계{" "}
          <strong className={styles.summaryHighlight}>{fmt(monthNewSum)}</strong>
        </p>
      )}
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
        {monthSummary ? (
          <Link
            href={monthNewSignupsHref(monthSummary.yearMonth)}
            className={styles.kpiLink}
            aria-label={`이 달 신규 가입 ${fmt(monthNewSum)} — 고객관리에서 보기`}
          >
            <KPICard label="이 달 신규 가입" value={fmt(monthNewSum)} />
          </Link>
        ) : (
          <Link
            href={newSignupsHref(data)}
            className={styles.kpiLink}
            aria-label={`최근 버킷 신규 ${fmt(last?.new_signups)} — 고객관리에서 보기`}
          >
            <KPICard label="최근 버킷 신규" value={fmt(last?.new_signups)} />
          </Link>
        )}
        <Link
          href="/admin/users"
          className={styles.kpiLink}
          aria-label={`${monthSummary ? "월말 누적 가입자" : "현재 누적 가입자"} ${fmt(last?.cumulative)} — 고객관리에서 보기`}
        >
          <KPICard
            label={monthSummary ? "월말 누적 가입자" : "현재 누적 가입자"}
            value={fmt(last?.cumulative)}
          />
        </Link>
        <Link
          href="/admin/users?withdrawn=false"
          className={styles.kpiLink}
          aria-label={`${monthSummary ? "월말 활성" : "현재 활성"} ${fmt(last?.active)} — 고객관리에서 보기`}
        >
          <KPICard
            label={monthSummary ? "월말 활성" : "현재 활성"}
            value={fmt(last?.active)}
          />
        </Link>
        <Link
          href="/admin/users?withdrawn=true"
          className={styles.kpiLink}
          aria-label={`${monthSummary ? "월말 누적 탈퇴" : "누적 탈퇴"} ${fmt(last?.withdrawn)} — 고객관리에서 보기`}
        >
          <KPICard
            label={monthSummary ? "월말 누적 탈퇴" : "누적 탈퇴"}
            value={fmt(last?.withdrawn)}
          />
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

/** "YYYY-MM" → "YYYY년 M월" */
function monthTitle(yearMonth: string): string {
  const [y, m] = yearMonth.split("-");
  if (!y || !m) return yearMonth;
  return `${y}년 ${Number(m)}월`;
}

/** 그 달 전체(1일~말일)에 가입한 사용자 목록으로 이동하는 링크. */
function monthNewSignupsHref(yearMonth: string): string {
  const [y, m] = yearMonth.split("-").map(Number);
  if (!y || !m) return "/admin/users";
  const last = new Date(y, m, 0).getDate();
  const from = `${yearMonth}-01`;
  const to = `${yearMonth}-${String(last).padStart(2, "0")}`;
  return `/admin/users?created_from=${from}&created_to=${to}&withdrawn=false`;
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

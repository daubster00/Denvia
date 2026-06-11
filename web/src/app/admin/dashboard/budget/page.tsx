"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBudgetCurrentMonth } from "@/features/admin-dashboard/api/budget";
import { BudgetGauge } from "@/features/admin-dashboard/components/BudgetGauge";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import { formatKRW } from "@/lib/format-currency";
import styles from "./page.module.css";

// OpenAI 청구는 보통 매월 1일에 전월 사용분이 정산됨.
// "2026-05" → "2026-06-01" KST 표기로 가공.
function nextOpenAiSettlementKst(yearMonth: string): string {
  const m = yearMonth.match(/^(\d{4})-(\d{2})$/);
  if (!m) return "—";
  let year = Number(m[1]);
  let month = Number(m[2]) + 1;
  if (month > 12) {
    year += 1;
    month = 1;
  }
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

// "2026-05" → "2026년 5월"
function formatYearMonthKo(ym: string): string {
  const m = ym.match(/^(\d{4})-(\d{2})$/);
  if (!m) return ym;
  return `${m[1]}년 ${Number(m[2])}월`;
}

// KST 기준 "YYYY-MM" 산출.
function computeCurrentKstYm(): string {
  const now = new Date();
  // KST = UTC+9. UTC 컴포넌트에 9시간 더해 KST 시각으로 변환.
  const kst = new Date(now.getTime() + 9 * 3600 * 1000);
  const y = kst.getUTCFullYear();
  const m = kst.getUTCMonth() + 1;
  return `${y}-${String(m).padStart(2, "0")}`;
}

// "YYYY-MM" + delta(개월) → "YYYY-MM" (음수 = 과거).
function addMonths(ym: string, delta: number): string {
  const m = ym.match(/^(\d{4})-(\d{2})$/);
  if (!m) return ym;
  // 1월 = index 0
  let total = Number(m[1]) * 12 + (Number(m[2]) - 1) + delta;
  const year = Math.floor(total / 12);
  const month = (total % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

export default function BudgetPage() {
  const qc = useQueryClient();
  const budgetWarning = useAdminEventsStore((s) => s.budgetWarning);

  // 현재 KST 월 — 클라이언트 렌더 시점 기준 (refresh 시 자동 갱신).
  const currentYm = useMemo(() => computeCurrentKstYm(), []);
  // offset = 0 → 이번 달, 1 → 한 달 전, 2 → 두 달 전, ...
  const [monthOffset, setMonthOffset] = useState(0);
  const selectedYm = useMemo(
    () => addMonths(currentYm, -monthOffset),
    [currentYm, monthOffset],
  );
  const isViewingCurrent = monthOffset === 0;

  const { data, error, refetch, isLoading } = useQuery({
    queryKey: ["admin", "budget", "current", selectedYm],
    queryFn: () => fetchBudgetCurrentMonth(isViewingCurrent ? undefined : selectedYm),
    // 이번 달일 때만 60초마다 자동 갱신 (실시간 사용량 반영).
    // 과거 달은 이미 굳은 값이라 폴링 불필요.
    refetchInterval: isViewingCurrent ? 60_000 : false,
  });

  useEffect(() => {
    if (budgetWarning && isViewingCurrent) {
      qc.invalidateQueries({ queryKey: ["admin", "budget", "current", selectedYm] });
    }
  }, [budgetWarning, qc, isViewingCurrent, selectedYm]);

  if (isLoading) {
    return <p className={styles.loading}>로딩 중…</p>;
  }

  if (error || !data) {
    return (
      <section className={styles.errorSection}>
        <p>예산 데이터를 불러오지 못했습니다.</p>
        <button className={styles.retryBtn} onClick={() => refetch()}>
          다시 시도
        </button>
      </section>
    );
  }

  const limitKrw = data.monthly_limit_krw;
  const spentKrw = data.spent_krw;
  const remainingKrw = Math.max(limitKrw - spentKrw, 0);
  const settlementDate = nextOpenAiSettlementKst(data.year_month);
  const isPast = data.is_past_month;

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>월 예산 모니터링</h1>
        <button className={styles.refreshBtn} onClick={() => refetch()} aria-label="새로고침">
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.spendCard}>
        <div className={styles.monthNav} role="group" aria-label="월 선택">
          <button
            type="button"
            className={styles.monthNavBtn}
            onClick={() => setMonthOffset((v) => v + 1)}
            aria-label="이전 달"
          >
            ←
          </button>
          <span className={styles.monthLabel}>
            {formatYearMonthKo(data.year_month)}
            {isPast && <span className={styles.pastTag}>지난 달</span>}
          </span>
          <button
            type="button"
            className={styles.monthNavBtn}
            onClick={() => setMonthOffset((v) => Math.max(0, v - 1))}
            disabled={isViewingCurrent}
            aria-label="다음 달"
          >
            →
          </button>
        </div>

        <div className={styles.spendMain}>
          <p className={styles.spendLabel}>
            {isPast ? "그 달 비용" : "이번 달 비용"}
          </p>
          <p className={styles.spendValue}>{formatKRW(spentKrw)}</p>
          {isViewingCurrent ? (
            <p className={styles.spendHint}>
              OpenAI 청구 예정일 {settlementDate} KST · 전월 사용분이 다음 달 1일에 정산됩니다.
            </p>
          ) : (
            <p className={styles.spendHint}>
              {formatYearMonthKo(data.year_month)} 한 달 사용분 (OpenAI 정산 완료)
            </p>
          )}
        </div>
      </div>

      <div className={styles.kpis}>
        <KPICard label="월 예산" value={formatKRW(limitKrw)} />
        <KPICard label="남은 예산" value={formatKRW(remainingKrw)} />
        <KPICard label="사용률" value={`${data.percent.toFixed(1)}%`} />
      </div>

      <div className={styles.gaugeSection}>
        <BudgetGauge
          current={spentKrw}
          max={limitKrw}
          killswitchActive={data.killswitch_active}
          killswitchMode={data.killswitch_mode}
        />
      </div>

      <nav className={styles.settingsLinks} aria-label="관련 설정">
        <Link
          href="/admin/settings#monthly-budget"
          className={styles.settingsLink}
        >
          월 예산 한도 변경 →
        </Link>
        <Link
          href="/admin/settings#chat-model"
          className={styles.settingsLink}
        >
          AI 모델 설정 →
        </Link>
      </nav>
    </section>
  );
}

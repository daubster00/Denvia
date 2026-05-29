"use client";

import { useEffect } from "react";
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

export default function BudgetPage() {
  const qc = useQueryClient();
  const budgetWarning = useAdminEventsStore((s) => s.budgetWarning);

  const { data, error, refetch, isLoading } = useQuery({
    queryKey: ["admin", "budget", "current"],
    queryFn: fetchBudgetCurrentMonth,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (budgetWarning) {
      qc.invalidateQueries({ queryKey: ["admin", "budget", "current"] });
    }
  }, [budgetWarning, qc]);

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

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>월 예산 모니터링</h1>
        <button className={styles.refreshBtn} onClick={() => refetch()} aria-label="새로고침">
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.spendCard}>
        <div className={styles.spendMain}>
          <p className={styles.spendLabel}>이번 달 비용 ({data.year_month})</p>
          <p className={styles.spendValue}>{formatKRW(spentKrw)}</p>
          <p className={styles.spendHint}>
            OpenAI 청구 예정일 {settlementDate} KST · 전월 사용분이 다음 달 1일에 정산됩니다.
          </p>
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

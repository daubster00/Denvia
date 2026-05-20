"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBudgetCurrentMonth } from "@/features/admin-dashboard/api/budget";
import { BudgetGauge } from "@/features/admin-dashboard/components/BudgetGauge";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import { formatKRW } from "@/lib/format-currency";
import styles from "./page.module.css";

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

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>월 예산 모니터링</h1>
        <button className={styles.refreshBtn} onClick={() => refetch()} aria-label="새로고침">
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.kpis}>
        <KPICard label="당월 토큰 비용" value={formatKRW(spentKrw)} />
        <KPICard label="월 예산" value={formatKRW(limitKrw)} />
        <KPICard label="남은 예산" value={formatKRW(remainingKrw)} />
      </div>

      <div className={styles.gaugeSection}>
        <BudgetGauge
          current={spentKrw}
          max={limitKrw}
          killswitchActive={data.killswitch_active}
          killswitchMode={data.killswitch_mode}
        />
      </div>
    </section>
  );
}

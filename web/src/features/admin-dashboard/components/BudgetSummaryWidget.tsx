"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBudgetCurrentMonth } from "../api/budget";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import { formatKRW } from "@/lib/format-currency";
import { BudgetGauge } from "./BudgetGauge";
import {
  DashboardWidget,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./BudgetSummaryWidget.module.css";

const QUERY_KEY = ["admin", "dashboard", "budget-current"] as const;

export function BudgetSummaryWidget() {
  const qc = useQueryClient();
  const budgetWarning = useAdminEventsStore((s) => s.budgetWarning);
  const killswitchStatus = useAdminEventsStore((s) => s.killswitchStatus);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchBudgetCurrentMonth,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (budgetWarning) qc.invalidateQueries({ queryKey: QUERY_KEY });
  }, [budgetWarning, qc]);

  useEffect(() => {
    if (killswitchStatus) qc.invalidateQueries({ queryKey: QUERY_KEY });
  }, [killswitchStatus, qc]);

  return (
    <DashboardWidget
      title="월 예산 사용률"
      caption="이번 달 토큰 비용과 한도를 한눈에 확인합니다."
      detailHref="/admin/dashboard/budget"
      footnote={isFetching ? "최신 정보를 불러오는 중…" : undefined}
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && (error || !data) && (
        <WidgetErrorState onRetry={() => refetch()} />
      )}
      {data && <BudgetSummaryBody data={data} />}
    </DashboardWidget>
  );
}

function BudgetSummaryBody({
  data,
}: {
  data: Awaited<ReturnType<typeof fetchBudgetCurrentMonth>>;
}) {
  const limitKrw = data.monthly_limit_krw;
  const spentKrw = data.spent_krw;
  const remainingKrw = Math.max(limitKrw - spentKrw, 0);
  const valueClass =
    data.status === "critical"
      ? styles.figureValueDanger
      : data.status === "warning"
        ? styles.figureValueWarning
        : "";

  return (
    <div className={styles.summary}>
      <BudgetGauge
        current={spentKrw}
        max={limitKrw}
        killswitchActive={data.killswitch_active}
        killswitchMode={data.killswitch_mode}
      />
      <dl className={styles.figures}>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>당월 비용</dt>
          <dd className={`${styles.figureValue} ${valueClass}`}>
            {formatKRW(spentKrw)}
          </dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>월 한도</dt>
          <dd className={styles.figureValue}>{formatKRW(limitKrw)}</dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>남은 예산</dt>
          <dd className={styles.figureValue}>{formatKRW(remainingKrw)}</dd>
        </div>
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>대상 월</dt>
          <dd className={styles.figureValue}>{data.year_month}</dd>
        </div>
      </dl>
    </div>
  );
}

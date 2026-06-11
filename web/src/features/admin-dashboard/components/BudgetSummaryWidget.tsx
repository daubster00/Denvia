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
    // queryFn에 함수를 직접 넘기면 React Query가 context를 자동 주입함 — 래핑 필수.
    queryFn: () => fetchBudgetCurrentMonth(),
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

// OpenAI 청구는 보통 매월 1일에 전월 사용분 정산.
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
  const settlementDate = nextOpenAiSettlementKst(data.year_month);

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
        <div className={styles.figureItem}>
          <dt className={styles.figureLabel}>OpenAI 청구 예정일</dt>
          <dd className={styles.figureValue}>{settlementDate}</dd>
        </div>
      </dl>
    </div>
  );
}

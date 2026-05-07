"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchBudgetCurrentMonth } from "@/features/admin-dashboard/api/budget";
import { fetchUserTokens } from "@/features/admin-dashboard/api/analytics";
import { fetchRagStatus } from "@/features/admin-rag/api/knowledge";
import { KPICard } from "@/features/admin-dashboard/components/KPICard";
import { BudgetSummaryWidget } from "@/features/admin-dashboard/components/BudgetSummaryWidget";
import { TokenTopUsersWidget } from "@/features/admin-dashboard/components/TokenTopUsersWidget";
import { RagStatusWidget } from "@/features/admin-dashboard/components/RagStatusWidget";
import { ComingSoonWidget } from "@/features/admin-dashboard/components/ComingSoonWidget";
import {
  SignupsSummaryWidget,
  SIGNUPS_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/SignupsSummaryWidget";
import {
  SubscribersSummaryWidget,
  SUBSCRIBERS_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/SubscribersSummaryWidget";
import {
  FeedbackSummaryWidget,
  FEEDBACK_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/FeedbackSummaryWidget";
import {
  SegmentsSummaryWidget,
  SEGMENTS_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/SegmentsSummaryWidget";
import {
  RevenueSummaryWidget,
  REVENUE_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/RevenueSummaryWidget";
import styles from "./dashboardHome.module.css";

const BUDGET_KEY = ["admin", "dashboard", "budget-current"] as const;
const TOKENS_KEY = [
  "admin",
  "dashboard",
  "user-tokens-top",
  { range: "month", per_page: 5 },
] as const;
const RAG_KEY = ["admin", "dashboard", "rag-status"] as const;

export default function AdminDashboardPage() {
  const qc = useQueryClient();

  const budgetQuery = useQuery({
    queryKey: BUDGET_KEY,
    queryFn: fetchBudgetCurrentMonth,
    refetchInterval: 60_000,
  });

  const tokensQuery = useQuery({
    queryKey: TOKENS_KEY,
    queryFn: () => fetchUserTokens({ range: "month", per_page: 5 }),
    refetchInterval: 60_000,
  });

  const ragQuery = useQuery({
    queryKey: RAG_KEY,
    queryFn: fetchRagStatus,
    refetchInterval: (query) =>
      query.state.data?.active_rebuild ? 5_000 : 60_000,
  });

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: BUDGET_KEY });
    qc.invalidateQueries({ queryKey: TOKENS_KEY });
    qc.invalidateQueries({ queryKey: RAG_KEY });
    qc.invalidateQueries({ queryKey: SIGNUPS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: SUBSCRIBERS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: FEEDBACK_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: SEGMENTS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: REVENUE_SUMMARY_KEY });
  }

  const budget = budgetQuery.data;
  const tokens = tokensQuery.data;
  const rag = ragQuery.data;

  const budgetPercentValue = budget ? `${budget.percent.toFixed(1)}%` : "—";
  const topUsersQuestionCount =
    tokens?.items.reduce((acc, row) => acc + row.question_count, 0) ?? null;
  const topCostUser = tokens?.items[0];
  const ragPendingValue =
    rag?.pending_changes_count !== undefined
      ? `${rag.pending_changes_count}건`
      : "—";

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>관리자 대시보드</h1>
          <p className={styles.caption}>
            운영 지표와 작업 상태를 한 화면에서 확인합니다.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={handleRefresh}
          aria-label="대시보드 새로고침"
        >
          ↻ 새로고침
        </button>
      </header>

      <div className={styles.kpiGrid}>
        <KPICard
          label="월 예산 사용률"
          value={budgetPercentValue}
          trend={
            budget && budget.status !== "normal"
              ? {
                  direction: "up",
                  text:
                    budget.status === "critical"
                      ? "위험"
                      : "주의",
                  tone:
                    budget.status === "critical" ? "error" : "warning",
                }
              : undefined
          }
        />
        <KPICard
          label="상위 5명 질의 수"
          value={
            topUsersQuestionCount !== null
              ? `${topUsersQuestionCount.toLocaleString()}건`
              : "—"
          }
        />
        <KPICard
          label="비용 TOP 사용자"
          value={
            topCostUser
              ? `$ ${Number(topCostUser.total_cost_usd).toFixed(4)}`
              : "—"
          }
        />
        <KPICard
          label="재빌드 대기 변경"
          value={ragPendingValue}
          trend={
            rag?.active_rebuild
              ? { direction: "flat", text: "재빌드 진행 중", tone: "warning" }
              : undefined
          }
        />
      </div>

      <div className={styles.mainGrid}>
        <BudgetSummaryWidget />
        <RagStatusWidget />
      </div>

      <div className={styles.analyticsGrid}>
        <TokenTopUsersWidget />
        <SignupsSummaryWidget />
        <SubscribersSummaryWidget />
        <FeedbackSummaryWidget />
        <SegmentsSummaryWidget />
        <RevenueSummaryWidget />
        <ComingSoonWidget
          title="이상탐지/CS"
          description="최근 이상 이벤트와 처리 대기 건을 표시합니다."
          storyRef="Epic 6/9에서 최근 이벤트와 처리 대기 건수 연결"
        />
      </div>
    </div>
  );
}

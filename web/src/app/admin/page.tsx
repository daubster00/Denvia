"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BudgetSummaryWidget } from "@/features/admin-dashboard/components/BudgetSummaryWidget";
import { TokenTopUsersWidget } from "@/features/admin-dashboard/components/TokenTopUsersWidget";
import {
  AnomalyCSSummaryWidget,
  ANOMALY_CS_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/AnomalyCSSummaryWidget";
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
import {
  AccessSummaryWidget,
  ACCESS_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/AccessSummaryWidget";
import {
  QuestionsSummaryWidget,
  QUESTIONS_SUMMARY_KEY,
} from "@/features/admin-dashboard/components/QuestionsSummaryWidget";
import styles from "./dashboardHome.module.css";

const BUDGET_KEY = ["admin", "dashboard", "budget-current"] as const;

export default function AdminDashboardPage() {
  const qc = useQueryClient();

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: BUDGET_KEY });
    qc.invalidateQueries({ queryKey: SIGNUPS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: SUBSCRIBERS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: FEEDBACK_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: SEGMENTS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: REVENUE_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: ANOMALY_CS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: ACCESS_SUMMARY_KEY });
    qc.invalidateQueries({ queryKey: QUESTIONS_SUMMARY_KEY });
  }

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

      <div className={styles.row2}>
        <AnomalyCSSummaryWidget />
        <FeedbackSummaryWidget />
      </div>

      <div className={styles.row2}>
        <BudgetSummaryWidget />
        <TokenTopUsersWidget />
      </div>

      <div className={styles.row3}>
        <SignupsSummaryWidget />
        <AccessSummaryWidget />
        <QuestionsSummaryWidget />
      </div>

      <div className={styles.row3}>
        <SegmentsSummaryWidget />
        <SubscribersSummaryWidget />
        <RevenueSummaryWidget />
      </div>
    </div>
  );
}

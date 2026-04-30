"use client";

/** AccountSummary — Story 4.3 AC-2. KPI 카드 그리드. */

import { useUsageSummary } from "../hooks/useUsageSummary";
import { PlanCard } from "./PlanCard";
import { SegmentCard } from "./SegmentCard";
import { SubscriptionCard } from "./SubscriptionCard";
import { UsageCard } from "./UsageCard";

import styles from "./AccountSummary.module.css";

export function AccountSummary() {
  const { data, isLoading, isError } = useUsageSummary();

  if (isLoading) {
    return (
      <div className={styles.grid} aria-busy="true">
        <p className={styles.placeholder}>마이페이지를 불러오는 중…</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={styles.grid}>
        <p className={styles.errorText}>
          정보를 불러오지 못했습니다 — 새로고침 해주세요.
        </p>
      </div>
    );
  }

  // pro / admin은 SubscriptionCard 자체 분기로 처리(none → null 반환).
  // free 사용자는 active/cancel_pending이 없으면 SubscriptionCard가 null.
  const subscriptionEnabled = data.subscription_status !== "admin";

  return (
    <div className={styles.grid}>
      <PlanCard
        subscriptionStatus={data.subscription_status}
        showSubscribeButton={data.show_subscribe_button}
      />
      <UsageCard
        monthCount={data.month_question_count}
        dailyUsed={data.daily_used}
        dailyLimit={data.daily_limit}
        dailyRemaining={data.daily_remaining}
        subscriptionStatus={data.subscription_status}
      />
      <SubscriptionCard enabled={subscriptionEnabled} />
      <SegmentCard
        segment={data.segment}
        yearsOfExperience={data.years_of_experience}
      />
    </div>
  );
}

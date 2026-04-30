"use client";

/** 사용량 카드 — Story 4.3 AC-2. 당월 누적 + 당일 진행률. */

import styles from "./UsageCard.module.css";

interface UsageCardProps {
  monthCount: number;
  dailyUsed: number;
  dailyLimit: number;
  dailyRemaining: number;
  subscriptionStatus: "free" | "pro" | "admin";
}

export function UsageCard({
  monthCount,
  dailyUsed,
  dailyLimit,
  dailyRemaining,
  subscriptionStatus,
}: UsageCardProps) {
  const showDaily = subscriptionStatus !== "pro";
  return (
    <section className={styles.card} aria-label="사용량">
      <div className={styles.row}>
        <span className={styles.label}>이번 달 질문</span>
        <span className={styles.value}>{monthCount}회</span>
      </div>
      {showDaily && (
        <div className={styles.dailyBlock}>
          <div className={styles.row}>
            <span className={styles.label}>오늘 사용량</span>
            <span className={styles.value}>
              {dailyUsed}/{dailyLimit}회
            </span>
          </div>
          <progress
            className={styles.progress}
            max={dailyLimit > 0 ? dailyLimit : 1}
            value={dailyUsed}
            aria-label="오늘 사용량"
          />
          <p className={styles.hint}>
            남은 횟수 {dailyRemaining}회 · 내일 00시 KST 초기화
          </p>
        </div>
      )}
    </section>
  );
}

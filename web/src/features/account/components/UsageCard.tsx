"use client";

/** 사용량 카드 — Story 4.3 AC-2. 당월 누적 + 당일 진행률. */

import styles from "./UsageCard.module.css";

interface UsageCardProps {
  monthCount: number;
  dailyUsed: number;
  dailyLimit: number;
  dailyRemaining: number;
  subscriptionStatus: "free" | "pro" | "admin";
  monthlyLimit: number;
  monthlyUsed: number;
  monthlyRemaining: number;
}

export function UsageCard({
  monthCount,
  dailyUsed,
  dailyLimit,
  dailyRemaining,
  subscriptionStatus,
  monthlyLimit,
  monthlyUsed,
  monthlyRemaining,
}: UsageCardProps) {
  const isPro = subscriptionStatus === "pro";
  return (
    <section className={styles.card} aria-label="사용량">
      <div className={styles.row}>
        <span className={styles.label}>이번 달 질문</span>
        <span className={styles.value}>{monthCount}회</span>
      </div>
      {isPro ? (
        <div className={styles.dailyBlock}>
          <div className={styles.row}>
            <span className={styles.label}>이번 달 사용량</span>
            <span className={styles.value}>
              {monthlyUsed}/{monthlyLimit}회
            </span>
          </div>
          <progress
            className={styles.progress}
            max={monthlyLimit > 0 ? monthlyLimit : 1}
            value={monthlyUsed}
            aria-label="이번 달 사용량"
          />
          <p className={styles.hint}>
            남은 횟수 {monthlyRemaining}회 · 매월 1일 00시 KST 초기화
          </p>
        </div>
      ) : (
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

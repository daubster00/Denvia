"use client";

/** 현재 플랜 카드 — Story 4.3 AC-2 / AC-4 (A-303 토글 연동). */

import Link from "next/link";

import { ProBadge } from "@/features/billing/components/ProBadge";

import styles from "./PlanCard.module.css";

interface PlanCardProps {
  subscriptionStatus: "free" | "pro" | "admin";
  showSubscribeButton: boolean;
}

export function PlanCard({ subscriptionStatus, showSubscribeButton }: PlanCardProps) {
  return (
    <section className={styles.card} aria-label="현재 플랜">
      <h2 className={styles.title}>현재 플랜</h2>
      {subscriptionStatus === "pro" && (
        <div className={styles.proBody}>
          <span className={styles.planName}>Pro — 무제한</span>
          <ProBadge size="lg" showIcon />
        </div>
      )}
      {subscriptionStatus === "admin" && (
        <div className={styles.body}>
          <span className={styles.planName}>관리자(무제한)</span>
        </div>
      )}
      {subscriptionStatus === "free" && (
        <div className={styles.body}>
          <span className={styles.planName}>Basic</span>
          {showSubscribeButton && (
            <Link href="/subscribe" className={styles.subscribeBtn}>
              구독하기
            </Link>
          )}
        </div>
      )}
    </section>
  );
}

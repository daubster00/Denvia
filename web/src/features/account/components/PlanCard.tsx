"use client";

/** 현재 플랜 카드 — Story 4.3 AC-2 / AC-4 (A-303 토글 연동). */

import Image from "next/image";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { CancelSubscriptionFlow } from "@/features/billing/components/CancelSubscriptionFlow";
import { useCurrentSubscription } from "@/features/billing/hooks/useCurrentSubscription";
import { useResumeSubscription } from "@/features/billing/hooks/useResumeSubscription";

import styles from "./PlanCard.module.css";

interface PlanCardProps {
  subscriptionStatus: "free" | "pro" | "admin";
  showSubscribeButton: boolean;
}

export function PlanCard({ subscriptionStatus, showSubscribeButton }: PlanCardProps) {
  const isPaid = subscriptionStatus !== "free";
  const iconBoxClass = `${styles.iconBox} ${isPaid ? styles.iconBoxPaid : styles.iconBoxFree}`;
  const iconSrc = isPaid
    ? "/symbol_no_background_color.png"
    : "/symbol_no_background_gray.png";
  const queryClient = useQueryClient();
  const [isCancelOpen, setIsCancelOpen] = useState(false);
  const { data: currentSub } = useCurrentSubscription({
    enabled: subscriptionStatus === "pro",
  });
  const resumeMutation = useResumeSubscription();

  const handleCancelSuccess = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
    queryClient.invalidateQueries({ queryKey: ["me", "usage-summary"] });
  }, [queryClient]);

  const handleResumeClick = useCallback(() => {
    if (resumeMutation.isPending) return;
    resumeMutation.mutate();
  }, [resumeMutation]);

  return (
    <section className={styles.card} aria-label="현재 플랜">
      <div className={iconBoxClass} aria-hidden="true">
        <Image
          src={iconSrc}
          alt=""
          width={36}
          height={36}
          className={styles.iconImage}
        />
      </div>
      <div className={styles.content}>
        <h2 className={styles.title}>현재 플랜</h2>
        {subscriptionStatus === "pro" && (
          <div className={styles.body}>
            <span className={styles.planName}>Pro — 무제한</span>
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
          </div>
        )}
        <p className={styles.description}>간편하고 스마트한 기본 플랜</p>
        {subscriptionStatus === "free" && showSubscribeButton && (
          <Link href="/subscribe" className={styles.subscribeBtn}>
            플랜 보기
          </Link>
        )}
        {subscriptionStatus === "pro" && currentSub?.status === "active" && (
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={() => setIsCancelOpen(true)}
          >
            구독 해지
          </button>
        )}
        {subscriptionStatus === "pro" && currentSub?.status === "cancel_pending" && (
          <button
            type="button"
            className={styles.resumeBtn}
            onClick={handleResumeClick}
            disabled={resumeMutation.isPending}
          >
            해지 철회
          </button>
        )}
      </div>
      <CancelSubscriptionFlow
        isOpen={isCancelOpen}
        onClose={() => setIsCancelOpen(false)}
        currentPeriodEnd={currentSub?.current_period_end ?? null}
        onCancelSuccess={handleCancelSuccess}
      />
    </section>
  );
}

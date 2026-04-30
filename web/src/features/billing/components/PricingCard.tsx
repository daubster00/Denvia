"use client";

/** PricingCard — UX-DR9. 플랜 카드 컴포넌트. */

import styles from "./PricingCard.module.css";
import type { PlanItem } from "../types";

interface PricingCardProps {
  plan: PlanItem;
  onCta?: () => void;
}

export function PricingCard({ plan, onCta }: PricingCardProps) {
  const { tier, name, price_krw, period, features, cta_label, is_recommended } = plan;
  const isCurrentPlan = cta_label.includes("현재");

  return (
    <div
      className={`${styles.card} ${is_recommended ? styles.recommended : ""} ${isCurrentPlan ? styles.currentPlan : ""}`}
      aria-label={`${name} 플랜`}
    >
      <div className={styles.header}>
        <h2 className={styles.planName}>{name}</h2>
        <div className={styles.priceRow}>
          <span className={styles.price}>
            {price_krw === 0 ? "0원" : `${price_krw.toLocaleString("ko-KR")}원`}
          </span>
          {period && <span className={styles.period}>{period}</span>}
        </div>
      </div>

      <ul className={styles.featureList} aria-label={`${name} 플랜 기능 목록`}>
        {features.map((feature) => (
          <li key={feature} className={styles.featureItem}>
            <span aria-hidden="true" className={styles.checkIcon}>✓</span>
            {feature}
          </li>
        ))}
      </ul>

      <button
        type="button"
        className={`${styles.ctaButton} ${tier === "pro" ? styles.ctaPro : styles.ctaFree}`}
        onClick={onCta}
        disabled={tier === "free"}
        aria-label={`${name} 플랜 ${cta_label}`}
      >
        {cta_label}
      </button>
    </div>
  );
}

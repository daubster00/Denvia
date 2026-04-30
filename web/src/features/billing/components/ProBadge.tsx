"use client";

/** ProBadge — UX-DR10. Pro 플랜 강조 배지. */

import styles from "./ProBadge.module.css";

interface ProBadgeProps {
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
}

export function ProBadge({ size = "md", showIcon = true }: ProBadgeProps) {
  return (
    <span className={`${styles.badge} ${styles[size]}`} aria-label="Pro 플랜">
      {showIcon && <span aria-hidden="true">👑</span>}
      <span>Pro</span>
    </span>
  );
}

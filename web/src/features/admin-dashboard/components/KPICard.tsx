"use client";

import styles from "./KPICard.module.css";

interface TrendInfo {
  direction: "up" | "down" | "flat";
  text?: string;
  tone?: "success" | "warning" | "error";
}

interface Props {
  label: string;
  value: string;
  trend?: TrendInfo;
  onClick?: () => void;
}

export function KPICard({ label, value, trend, onClick }: Props) {
  return (
    <article
      className={styles.card}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <dl>
        <dt className={styles.label}>{label}</dt>
        <dd className={styles.value}>{value}</dd>
        {trend && (
          <dd className={`${styles.trend} ${styles[trend.tone ?? "success"]}`}>
            {trend.direction === "up"
              ? "▲"
              : trend.direction === "down"
                ? "▼"
                : "—"}
            {" "}
            {trend.text}
          </dd>
        )}
      </dl>
    </article>
  );
}

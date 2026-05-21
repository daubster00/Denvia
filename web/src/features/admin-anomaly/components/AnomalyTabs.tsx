"use client";

import type { AnomalyType } from "@/features/admin-anomaly/api/anomaly";
import { ANOMALY_TYPE_LABELS } from "@/features/admin-users/labels";
import styles from "./AnomalyTabs.module.css";

interface Props {
  activeType: AnomalyType | null;
  onChange: (next: AnomalyType | null) => void;
}

const ALL_TYPES: AnomalyType[] = [
  "login_brute_force",
  "concurrent_ip_login",
  "repeated_question",
  "recovery_abuse",
  "rapid_followup_questions",
];

export function AnomalyTabs({ activeType, onChange }: Props) {
  return (
    <div className={styles.tabs} role="tablist" aria-label="이상 이벤트 분류">
      <button
        type="button"
        role="tab"
        aria-selected={activeType === null}
        className={activeType === null ? styles.tabActive : styles.tab}
        onClick={() => onChange(null)}
      >
        전체
      </button>
      {ALL_TYPES.map((type) => (
        <button
          key={type}
          type="button"
          role="tab"
          aria-selected={activeType === type}
          className={activeType === type ? styles.tabActive : styles.tab}
          onClick={() => onChange(type)}
          data-testid={`anomaly-tab-${type}`}
        >
          {ANOMALY_TYPE_LABELS[type] ?? type}
        </button>
      ))}
    </div>
  );
}

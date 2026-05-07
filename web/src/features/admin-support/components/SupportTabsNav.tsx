"use client";

import styles from "./SupportTabsNav.module.css";

export type SupportTabKey = "inquiries" | "refunds";

interface Props {
  activeTab: SupportTabKey;
  inquiryCount: number;
  refundCount: number;
  onChange: (next: SupportTabKey) => void;
}

const TABS: Array<{ key: SupportTabKey; label: string }> = [
  { key: "inquiries", label: "문의" },
  { key: "refunds", label: "환불 검토" },
];

export function SupportTabsNav({ activeTab, inquiryCount, refundCount, onChange }: Props) {
  return (
    <nav className={styles.bar} role="tablist" aria-label="CS 화면 탭">
      {TABS.map((tab) => {
        const active = tab.key === activeTab;
        const count = tab.key === "inquiries" ? inquiryCount : refundCount;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={active ? `${styles.tab} ${styles.tabActive}` : styles.tab}
            onClick={() => onChange(tab.key)}
            data-testid={`support-tab-${tab.key}`}
          >
            <span className={styles.tabLabel}>{tab.label}</span>
            <span
              className={count > 0 ? styles.badgeActive : styles.badge}
              aria-label={`${count}건`}
            >
              {count}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

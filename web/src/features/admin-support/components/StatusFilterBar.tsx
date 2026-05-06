"use client";

import type { InquiryStatus } from "@/features/admin-support/api/inquiries";
import { formatInquiryStatus } from "@/features/admin-support/labels";
import styles from "./StatusFilterBar.module.css";

const STATUS_OPTIONS: Array<InquiryStatus | "all"> = [
  "all",
  "open",
  "in_progress",
  "resolved",
];

interface Props {
  value: InquiryStatus | null;
  onChange: (next: InquiryStatus | null) => void;
  onRefresh: () => void;
  isFetching: boolean;
}

export function StatusFilterBar({
  value,
  onChange,
  onRefresh,
  isFetching,
}: Props) {
  return (
    <div className={styles.bar} role="toolbar" aria-label="문의 필터">
      <div className={styles.tabs} role="tablist" aria-label="상태 필터">
        {STATUS_OPTIONS.map((option) => {
          const active = (option === "all" && value === null) || option === value;
          return (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={active}
              className={
                active ? `${styles.tab} ${styles.tabActive}` : styles.tab
              }
              onClick={() => onChange(option === "all" ? null : option)}
            >
              {option === "all" ? "전체" : formatInquiryStatus(option)}
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className={styles.refreshButton}
        onClick={onRefresh}
        disabled={isFetching}
        aria-label="목록 새로고침"
      >
        {isFetching ? "불러오는 중…" : "새로고침"}
      </button>
    </div>
  );
}

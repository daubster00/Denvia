"use client";

import { useEffect, useState } from "react";
import type { InquiryStatus } from "@/features/admin-support/api/inquiries";
import { formatInquiryStatus } from "@/features/admin-support/labels";
import styles from "./StatusFilterBar.module.css";

const STATUS_OPTIONS: InquiryStatus[] = ["open", "in_progress", "resolved"];

interface Props {
  statusIn: Set<InquiryStatus>;
  q: string;
  from: string;
  to: string;
  onStatusToggle: (status: InquiryStatus) => void;
  onStatusReset: () => void;
  onQChange: (next: string) => void;
  onFromChange: (next: string) => void;
  onToChange: (next: string) => void;
  onRefresh: () => void;
  isFetching: boolean;
}

const Q_DEBOUNCE_MS = 300;

export function StatusFilterBar({
  statusIn,
  q,
  from,
  to,
  onStatusToggle,
  onStatusReset,
  onQChange,
  onFromChange,
  onToChange,
  onRefresh,
  isFetching,
}: Props) {
  const [localQ, setLocalQ] = useState(q);

  useEffect(() => {
    setLocalQ(q);
  }, [q]);

  useEffect(() => {
    const handle = setTimeout(() => {
      if (localQ !== q) onQChange(localQ);
    }, Q_DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localQ]);

  const allSelected = statusIn.size === 0;

  return (
    <div className={styles.bar} role="toolbar" aria-label="문의 필터">
      <div className={styles.statusGroup} role="group" aria-label="상태 필터">
        <button
          type="button"
          className={
            allSelected ? `${styles.statusChip} ${styles.statusChipActive}` : styles.statusChip
          }
          aria-pressed={allSelected}
          onClick={onStatusReset}
        >
          전체
        </button>
        {STATUS_OPTIONS.map((status) => {
          const active = statusIn.has(status);
          return (
            <button
              key={status}
              type="button"
              aria-pressed={active}
              className={
                active ? `${styles.statusChip} ${styles.statusChipActive}` : styles.statusChip
              }
              onClick={() => onStatusToggle(status)}
            >
              {formatInquiryStatus(status)}
            </button>
          );
        })}
      </div>

      <div className={styles.inlineGroup}>
        <label className={styles.dateField}>
          <span className={styles.dateLabel}>기간</span>
          <input
            type="date"
            className={styles.dateInput}
            value={from}
            max={to || undefined}
            onChange={(e) => onFromChange(e.target.value)}
            aria-label="시작일"
          />
        </label>
        <span aria-hidden="true" className={styles.dateSeparator}>
          ~
        </span>
        <label className={styles.dateField}>
          <input
            type="date"
            className={styles.dateInput}
            value={to}
            min={from || undefined}
            onChange={(e) => onToChange(e.target.value)}
            aria-label="종료일"
          />
        </label>
      </div>

      <div className={styles.searchGroup}>
        <input
          type="search"
          placeholder="제목·본문·이메일 검색"
          value={localQ}
          maxLength={100}
          onChange={(e) => setLocalQ(e.target.value)}
          aria-label="검색어"
          className={styles.searchInput}
        />
        <button
          type="button"
          className={styles.refreshButton}
          onClick={onRefresh}
          disabled={isFetching}
          aria-label="목록 새로고침"
        >
          {isFetching ? "..." : "새로고침"}
        </button>
      </div>
    </div>
  );
}

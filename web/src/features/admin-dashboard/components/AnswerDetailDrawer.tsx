"use client";

import { useEffect, useCallback } from "react";
import type { FeedbackItem } from "../api/analytics";
import styles from "./AnswerDetailDrawer.module.css";

interface AnswerDetailDrawerProps {
  item: FeedbackItem | null;
  onClose: () => void;
}

export function AnswerDetailDrawer({ item, onClose }: AnswerDetailDrawerProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (!item) return;
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [item, handleKeyDown]);

  if (!item) return null;

  const ratingLabel = item.rating === "good" ? "👍 GOOD" : "👎 BAD";
  const kstFormatted = formatKst(item.created_at);

  return (
    <>
      <div
        className={styles.backdrop}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="답변 상세"
        className={styles.drawer}
      >
        <header className={styles.drawerHeader}>
          <h2 className={styles.drawerTitle}>답변 상세</h2>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Drawer 닫기"
          >
            ✕
          </button>
        </header>

        <div className={styles.drawerBody}>
          <section className={styles.section}>
            <h3 className={styles.sectionLabel}>질문</h3>
            <p className={styles.sectionContent}>{item.question_text}</p>
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionLabel}>답변</h3>
            <p className={styles.sectionContent}>
              {item.answer_text ?? "—"}
            </p>
          </section>

          <dl className={styles.meta}>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>피드백</dt>
              <dd
                className={`${styles.metaValue} ${
                  item.rating === "good" ? styles.ratingGood : styles.ratingBad
                }`}
              >
                {ratingLabel}
              </dd>
            </div>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>가입유형</dt>
              <dd className={styles.metaValue}>{item.segment ?? "—"}</dd>
            </div>
            <div className={styles.metaRow}>
              <dt className={styles.metaLabel}>제출일시</dt>
              <dd className={styles.metaValue}>{kstFormatted}</dd>
            </div>
          </dl>
        </div>
      </div>
    </>
  );
}

function formatKst(iso: string): string {
  try {
    const d = new Date(iso);
    const kst = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
    return kst;
  } catch {
    return iso;
  }
}

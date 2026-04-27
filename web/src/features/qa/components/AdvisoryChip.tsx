"use client";

import styles from "./AdvisoryChip.module.css";

export function AdvisoryChip() {
  return (
    <p
      role="note"
      aria-label="이 답변은 임상 참고용입니다"
      className={styles.chip}
    >
      임상 참고용 답변 · 전문가 판단 우선
    </p>
  );
}

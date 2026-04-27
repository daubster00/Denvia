"use client";

import styles from "./AdvisoryChip.module.css";

/**
 * 면책 고지 칩 — 하단 상시 표시 (NFR-C6).
 * "본 답변은 참고용이며 의학적 판단은 전문가 책임"
 */
export function AdvisoryChip() {
  return (
    <p role="note" className={styles.chip}>
      본 답변은 참고용이며 의학적 판단은 전문가 책임
    </p>
  );
}

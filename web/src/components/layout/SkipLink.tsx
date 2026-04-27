"use client";

import styles from "./SkipLink.module.css";

/** 접근성 Skip link — 포커스 시 표시, #main으로 이동 (WCAG 2.4.1, UX-DR24) */
export function SkipLink() {
  return (
    <a href="#main" className={styles.skipLink}>
      메인 콘텐츠로 건너뛰기
    </a>
  );
}

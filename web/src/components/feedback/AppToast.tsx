"use client";

/** AppToast — Story 4.3.
 *
 * useToastStore.current를 구독하는 글로벌 단일 토스트.
 * 자동 dismiss(2초). 외부 라이브러리 미사용(NFR-P5).
 */

import { useToastStore } from "@/stores/toast-store";

import styles from "./AppToast.module.css";

export function AppToast() {
  const current = useToastStore((s) => s.current);

  if (!current) return null;

  return (
    <div className={styles.toast} role="status" aria-live="polite">
      {current.message}
    </div>
  );
}

"use client";

import { useEffect, useRef } from "react";
import styles from "./ConfirmDialog.module.css";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 관리자 전용 확인 다이얼로그 — UX-DR27 규칙 적용.
 * - 정방향 액션(확인) 항상 오른쪽
 * - focus trap + ESC 닫기 + aria-modal
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "확인",
  cancelLabel = "취소",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      role="presentation"
      className={styles.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={description ? "confirm-dialog-desc" : undefined}
        className={styles.dialog}
      >
        <h2
          id="confirm-dialog-title"
          className={
            description
              ? `${styles.title} ${styles.titleWithDescription}`
              : styles.title
          }
        >
          {title}
        </h2>
        {description && (
          <p id="confirm-dialog-desc" className={styles.description}>
            {description}
          </p>
        )}

        {/* 정방향(확인) 항상 오른쪽 — UX-DR27 */}
        <div className={styles.actions}>
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className={styles.cancelBtn}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={
              danger
                ? `${styles.confirmBtn} ${styles.confirmBtnDanger}`
                : styles.confirmBtn
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

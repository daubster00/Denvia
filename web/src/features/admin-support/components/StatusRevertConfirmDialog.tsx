"use client";

import { useEffect, useRef } from "react";
import type { InquiryStatus } from "@/features/admin-support/api/inquiries";
import { formatInquiryStatus } from "@/features/admin-support/labels";
import styles from "./StatusRevertConfirmDialog.module.css";

interface Props {
  open: boolean;
  currentStatus: InquiryStatus;
  requestedStatus: InquiryStatus;
  isPending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function StatusRevertConfirmDialog({
  open,
  currentStatus,
  requestedStatus,
  isPending,
  onCancel,
  onConfirm,
}: Props) {
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmBtnRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <>
      <div className={styles.backdrop} onClick={onCancel} aria-hidden="true" />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="status-revert-title"
        className={styles.dialog}
      >
        <h3 id="status-revert-title" className={styles.title}>
          상태를 되돌리시겠습니까?
        </h3>
        <p className={styles.body}>
          완료된 문의를 <strong>{formatInquiryStatus(requestedStatus)}</strong>으로
          되돌립니다. 사용자에게는 별도 알림이 발송되지 않습니다.
        </p>
        <p className={styles.meta}>
          현재: {formatInquiryStatus(currentStatus)} → 변경 후:{" "}
          {formatInquiryStatus(requestedStatus)}
        </p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.cancelButton}
            onClick={onCancel}
            disabled={isPending}
          >
            취소
          </button>
          <button
            type="button"
            ref={confirmBtnRef}
            className={styles.confirmButton}
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? "처리 중…" : "되돌리기"}
          </button>
        </div>
      </div>
    </>
  );
}

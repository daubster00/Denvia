"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./RefundActionConfirmDialog.module.css";

export type RefundActionKind = "approve" | "deny";

interface Props {
  open: boolean;
  kind: RefundActionKind;
  amountKrw: number;
  isPending: boolean;
  errorMessage: string | null;
  onCancel: () => void;
  onConfirm: (note: string) => void;
}

const KRW = new Intl.NumberFormat("ko-KR");

export function RefundActionConfirmDialog({
  open,
  kind,
  amountKrw,
  isPending,
  errorMessage,
  onCancel,
  onConfirm,
}: Props) {
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) {
      setNote("");
      return;
    }
    noteRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const trimmed = note.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= 1000 && !isPending;
  const isApprove = kind === "approve";

  return (
    <>
      <div className={styles.backdrop} onClick={onCancel} aria-hidden="true" />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="refund-action-title"
        className={styles.dialog}
      >
        <h3 id="refund-action-title" className={styles.title}>
          {isApprove ? "환불을 승인하시겠습니까?" : "환불을 거부하시겠습니까?"}
        </h3>
        <p className={styles.body}>
          {isApprove
            ? "사용자에게 알림톡과 쪽지함 통지가 발송되며 PG 환불이 즉시 진행됩니다. (취소 불가)"
            : "사용자에게 거부 알림톡과 쪽지함 통지가 발송됩니다. 결제는 그대로 유지됩니다."}
        </p>
        <p className={styles.amountLine}>
          환불 금액: <strong>{KRW.format(amountKrw)}원</strong>
        </p>
        <label className={styles.label} htmlFor="refund-action-note">
          관리자 메모 (필수, 최대 1000자)
        </label>
        <textarea
          id="refund-action-note"
          ref={noteRef}
          className={styles.textarea}
          value={note}
          onChange={(e) => setNote(e.target.value.slice(0, 1000))}
          rows={4}
          maxLength={1000}
          placeholder={
            isApprove
              ? "예: 사용자 요청 + 7일 이내 + 질의 0건 → 정상 환불 처리"
              : "예: 7일 초과 + 질의 12건 사용 → 환불 거부, 사유 안내 필요"
          }
          disabled={isPending}
        />
        <div className={styles.metaRow}>
          <span className={styles.charCount}>{note.length} / 1000</span>
        </div>
        {errorMessage ? (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        ) : null}
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
            className={isApprove ? styles.approveButton : styles.denyButton}
            onClick={() => onConfirm(trimmed)}
            disabled={!canSubmit}
          >
            {isPending
              ? "처리 중…"
              : isApprove
                ? "승인 진행"
                : "거부 처리"}
          </button>
        </div>
      </div>
    </>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import type { RefundQueueItem } from "@/features/admin-support/api/refunds";
import {
  REFUND_QUEUE_STATUS_LABELS,
  formatRefundReason,
} from "@/features/admin-support/labels";
import { useApproveRefund } from "@/features/admin-support/hooks/useApproveRefund";
import { useDenyRefund } from "@/features/admin-support/hooks/useDenyRefund";
import {
  RefundActionConfirmDialog,
  type RefundActionKind,
} from "./RefundActionConfirmDialog";
import styles from "./RefundReviewDrawer.module.css";

interface Props {
  open: boolean;
  item: RefundQueueItem | null;
  onClose: () => void;
}

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const KRW = new Intl.NumberFormat("ko-KR");

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input, select, textarea';

export function RefundReviewDrawer({ open, item, onClose }: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [confirmKind, setConfirmKind] = useState<RefundActionKind | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const approveMutation = useApproveRefund();
  const denyMutation = useDenyRefund();

  useEffect(() => {
    setConfirmKind(null);
    setFeedback(null);
    setErrorMsg(null);
  }, [item?.queue_id]);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && confirmKind === null) {
        onClose();
        return;
      }
      if (e.key === "Tab" && drawerRef.current) {
        const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
          FOCUSABLE_SELECTOR,
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose, confirmKind]);

  if (!open || !item) return null;

  const isPending = approveMutation.isPending || denyMutation.isPending;
  const isPendingItem = item.status === "pending";

  function handleConfirm(note: string) {
    if (!item) return;
    setErrorMsg(null);
    if (confirmKind === "approve") {
      approveMutation.mutate(
        { queueId: item.queue_id, note },
        {
          onSuccess: () => {
            setConfirmKind(null);
            setFeedback("환불이 승인되어 처리되었습니다.");
          },
          onError: (err: any) => {
            const code = err?.code ?? "UNKNOWN_ERROR";
            const msg =
              code === "PG_REFUND_FAILED"
                ? `PG가 환불을 거부했습니다. (${err?.details?.pg_error_code ?? "코드 미상"})`
                : (err?.message ?? "환불 승인에 실패했습니다.");
            setErrorMsg(msg);
          },
        },
      );
    } else if (confirmKind === "deny") {
      denyMutation.mutate(
        { queueId: item.queue_id, note },
        {
          onSuccess: () => {
            setConfirmKind(null);
            setFeedback("환불이 거부 처리되었습니다.");
          },
          onError: (err: any) => {
            setErrorMsg(err?.message ?? "환불 거부에 실패했습니다.");
          },
        },
      );
    }
  }

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <aside
        ref={drawerRef}
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-labelledby="refund-review-title"
      >
        <header className={styles.header}>
          <h2 id="refund-review-title" className={styles.title}>
            환불 요청 검토
          </h2>
          <button
            type="button"
            ref={closeBtnRef}
            className={styles.closeButton}
            onClick={onClose}
            aria-label="닫기"
          >
            ×
          </button>
        </header>

        <div className={styles.body}>
          <section className={styles.section}>
            <h3 className={styles.amount}>{KRW.format(item.amount_krw)}원</h3>
            <p className={styles.subInfo}>
              {item.user_email_masked} ·{" "}
              {item.card_company ?? "-"}{" "}
              {item.card_last4 ? `****${item.card_last4}` : ""}
            </p>
            <span className={styles.statusPill} data-status={item.status}>
              {REFUND_QUEUE_STATUS_LABELS[item.status]}
            </span>
          </section>

          <section className={styles.section}>
            <h4 className={styles.sectionLabel}>환불 메타</h4>
            <dl className={styles.metaList}>
              <div className={styles.metaRow}>
                <dt>요청일</dt>
                <dd>{formatDateTime(item.requested_at)}</dd>
              </div>
              <div className={styles.metaRow}>
                <dt>결제 후 경과</dt>
                <dd>{item.days_since_charge}일</dd>
              </div>
              <div className={styles.metaRow}>
                <dt>구간 내 질의</dt>
                <dd>{item.qa_count_during_period}건</dd>
              </div>
              <div className={styles.metaRow}>
                <dt>자동 분기 사유</dt>
                <dd>{formatRefundReason(item.reason_code)}</dd>
              </div>
            </dl>
          </section>

          {item.reason_text ? (
            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>사용자 입력 사유</h4>
              <p className={styles.reasonText}>{item.reason_text}</p>
            </section>
          ) : null}

          {item.status !== "pending" ? (
            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>검토 결과</h4>
              <dl className={styles.metaList}>
                <div className={styles.metaRow}>
                  <dt>검토자</dt>
                  <dd>{item.reviewer_user_email_masked ?? "—"}</dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>검토일</dt>
                  <dd>{formatDateTime(item.reviewed_at)}</dd>
                </div>
                <div className={styles.metaRow}>
                  <dt>관리자 메모</dt>
                  <dd className={styles.notePreview}>{item.reviewer_note ?? "—"}</dd>
                </div>
              </dl>
            </section>
          ) : null}

          {feedback ? (
            <p className={styles.feedback} role="status">
              {feedback}
            </p>
          ) : null}

          {isPendingItem ? (
            <section className={styles.section}>
              <h4 className={styles.sectionLabel}>액션</h4>
              <div className={styles.actions}>
                <button
                  type="button"
                  className={styles.approveButton}
                  onClick={() => setConfirmKind("approve")}
                  disabled={isPending}
                >
                  승인
                </button>
                <button
                  type="button"
                  className={styles.denyButton}
                  onClick={() => setConfirmKind("deny")}
                  disabled={isPending}
                >
                  거부
                </button>
              </div>
            </section>
          ) : null}
        </div>
      </aside>

      <RefundActionConfirmDialog
        open={confirmKind !== null}
        kind={confirmKind ?? "approve"}
        amountKrw={item.amount_krw}
        isPending={isPending}
        errorMessage={errorMsg}
        onCancel={() => {
          if (!isPending) {
            setConfirmKind(null);
            setErrorMsg(null);
          }
        }}
        onConfirm={handleConfirm}
      />
    </>
  );
}

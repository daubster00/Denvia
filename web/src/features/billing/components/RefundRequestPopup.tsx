"use client";

/**
 * RefundRequestPopup — 결제 환불 요청 모달 (Story 3.6).
 *
 * step 상태:
 *   form         — 결제 정보 + reason textarea + Submit/Cancel
 *   submitting   — spinner
 *   done_refunded — 자동 환불 성공
 *   done_queued  — 수동 검토 큐 INSERT (reason_code별 카피)
 *   error        — errorMessage + 다시 시도
 */

import { useCallback, useState } from "react";

import { useRequestRefund } from "../hooks/useRequestRefund";
import type {
  RefundPaymentInfo,
  RefundReasonCode,
  RefundResult,
} from "../types";
import styles from "./RefundRequestPopup.module.css";

export interface RefundRequestPopupProps {
  isOpen: boolean;
  onClose: () => void;
  payment: RefundPaymentInfo;
  onSuccess?: (result: RefundResult) => void;
}

type FlowStep =
  | "form"
  | "submitting"
  | "done_refunded"
  | "done_queued"
  | "error";

interface ApiErrorDetail {
  code?: string;
  message?: string;
  status?: number;
}

function formatKoreanDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return `${d.getFullYear()}년 ${String(d.getMonth() + 1).padStart(2, "0")}월 ${String(
    d.getDate()
  ).padStart(2, "0")}일`;
}

function formatAmount(amount: number): string {
  return amount.toLocaleString("ko-KR");
}

function reasonCodeCopy(code: RefundReasonCode | null | undefined): string {
  switch (code) {
    case "period_exceeded":
      return "결제 후 7일이 지나 자동 환불이 불가능합니다. 관리자 검토 후 안내드리겠습니다.";
    case "qa_count_exceeded":
      return "구독 기간 동안 사용 이력이 있어 자동 환불이 불가능합니다. 관리자 검토 후 안내드리겠습니다.";
    case "both":
      return "결제 후 7일 + 사용 이력 모두 해당되어 자동 환불이 불가능합니다. 관리자 검토 후 안내드리겠습니다.";
    default:
      return "관리자 검토 후 안내드리겠습니다.";
  }
}

function pickErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) {
    const msg = (err as { message: unknown }).message;
    if (typeof msg === "string" && msg.length > 0) {
      // 502 카피 매핑
      if (msg.includes("BILLING_PROVIDER_UNAVAILABLE")) {
        return "결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.";
      }
      if (msg.includes("REFUND_ALREADY_PROCESSED")) {
        return "이미 환불된 결제입니다.";
      }
      if (msg.includes("REFUND_ALREADY_REQUESTED")) {
        return "환불이 이미 요청되었습니다.";
      }
      if (msg.includes("PAYMENT_NOT_REFUNDABLE")) {
        return "환불할 수 없는 결제입니다.";
      }
      if (msg.includes("PAYMENT_NOT_FOUND")) {
        return "결제 내역을 찾을 수 없습니다.";
      }
      return msg;
    }
  }
  return "환불 처리 중 오류가 발생했습니다.";
}

export function RefundRequestPopup({
  isOpen,
  onClose,
  payment,
  onSuccess,
}: RefundRequestPopupProps) {
  const [step, setStep] = useState<FlowStep>("form");
  const [reason, setReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refundedAt, setRefundedAt] = useState<string | null>(null);
  const [refundedAmount, setRefundedAmount] = useState<number | null>(null);
  const [reasonCode, setReasonCode] = useState<RefundReasonCode | null>(null);

  const refundMutation = useRequestRefund();

  const handleSubmit = useCallback(async () => {
    setStep("submitting");
    setErrorMessage(null);
    try {
      const result = await refundMutation.mutateAsync({
        paymentId: payment.id,
        reason: reason.trim() || undefined,
      });

      if (result.status === "refunded") {
        setRefundedAt(result.refunded_at);
        setRefundedAmount(result.amount_krw);
        setStep("done_refunded");
      } else {
        setReasonCode(result.reason_code ?? null);
        setStep("done_queued");
      }
      onSuccess?.(result);
    } catch (err: unknown) {
      setErrorMessage(pickErrorMessage(err));
      setStep("error");
    }
  }, [payment.id, reason, refundMutation, onSuccess]);

  const handleRetry = useCallback(() => {
    setStep("form");
    setErrorMessage(null);
  }, []);

  const handleClose = useCallback(() => {
    setReason("");
    setErrorMessage(null);
    setRefundedAt(null);
    setRefundedAmount(null);
    setReasonCode(null);
    setStep("form");
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label="환불 요청"
    >
      <div className={styles.modal}>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={handleClose}
          aria-label="닫기"
        >
          ✕
        </button>

        {step === "form" && (
          <div className={styles.content}>
            <h2 className={styles.title}>환불 요청</h2>
            <p className={styles.notice}>
              결제 후 7일 이내 + 구독 기간 동안 사용 이력이 없는 경우 자동
              환불됩니다. 그렇지 않다면 관리자 검토 후 안내드립니다.
            </p>
            <div className={styles.paymentCard} aria-label="환불 대상 결제 정보">
              <div className={styles.paymentRow}>
                <span className={styles.paymentLabel}>결제 금액</span>
                <span className={styles.paymentValue}>
                  {formatAmount(payment.amount_krw)}원
                </span>
              </div>
              <div className={styles.paymentRow}>
                <span className={styles.paymentLabel}>결제일</span>
                <span className={styles.paymentValue}>
                  {formatKoreanDate(payment.charged_at)}
                </span>
              </div>
              <div className={styles.paymentRow}>
                <span className={styles.paymentLabel}>카드</span>
                <span className={styles.paymentValue}>
                  {payment.card_last4
                    ? `**** ${payment.card_last4}`
                    : "정보 없음"}
                </span>
              </div>
            </div>
            <div>
              <label className={styles.label} htmlFor="refund-reason">
                환불 사유 (선택)
              </label>
              <textarea
                id="refund-reason"
                className={styles.textarea}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="환불을 요청하시는 이유를 알려주세요. (선택 입력)"
                maxLength={500}
              />
            </div>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={handleClose}
              >
                취소
              </button>
              <button
                type="button"
                className={styles.dangerBtn}
                onClick={handleSubmit}
              >
                환불 요청하기
              </button>
            </div>
          </div>
        )}

        {step === "submitting" && (
          <div className={styles.content}>
            <div
              className={styles.spinner}
              role="status"
              aria-label="환불 처리 중"
            />
            <p className={styles.statusText}>환불 요청을 처리 중입니다...</p>
          </div>
        )}

        {step === "done_refunded" && (
          <div className={styles.content}>
            <p className={styles.successIcon}>✓</p>
            <h2 className={styles.title}>환불이 완료되었습니다</h2>
            <p className={styles.notice}>
              {refundedAmount !== null
                ? `${formatAmount(refundedAmount)}원이 환불 처리되었습니다.`
                : "환불이 처리되었습니다."}
              <br />
              처리일: {formatKoreanDate(refundedAt)}
              <br />
              구독이 즉시 종료되며 다음 결제는 청구되지 않습니다.
            </p>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={handleClose}
              >
                확인
              </button>
            </div>
          </div>
        )}

        {step === "done_queued" && (
          <div className={styles.content}>
            <p className={styles.successIcon}>✓</p>
            <h2 className={styles.title}>환불 요청이 접수되었습니다</h2>
            <p className={styles.notice}>{reasonCodeCopy(reasonCode)}</p>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={handleClose}
              >
                확인
              </button>
            </div>
          </div>
        )}

        {step === "error" && (
          <div className={styles.content}>
            <p className={styles.errorText}>
              {errorMessage || "환불 처리 중 오류가 발생했습니다."}
            </p>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryBtn}
                onClick={handleClose}
              >
                닫기
              </button>
              <button
                type="button"
                className={styles.dangerBtn}
                onClick={handleRetry}
              >
                다시 시도
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

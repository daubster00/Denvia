"use client";

/**
 * CancelSubscriptionFlow — 구독 해지 모달 (Story 3.5).
 *
 * step 상태:
 *   form       — reason textarea + Submit/Cancel
 *   submitting — spinner
 *   done       — "해지가 예약되었습니다 ({effective_at}부터 적용)"
 *   error      — errorMessage + 다시 시도
 */

import { useCallback, useState } from "react";

import { useCancelSubscription } from "../hooks/useCancelSubscription";
import styles from "./CancelSubscriptionFlow.module.css";

export interface CancelSubscriptionFlowProps {
  isOpen: boolean;
  onClose: () => void;
  /** 적용 예정일(ISO) — 모달 안내 카피에 표시. */
  currentPeriodEnd: string | null;
  onCancelSuccess?: () => void;
}

type FlowStep = "form" | "submitting" | "done" | "error";

function formatKoreanDate(iso: string | null | undefined): string {
  if (!iso) return "다음 결제일";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "다음 결제일";
  return `${d.getFullYear()}년 ${String(d.getMonth() + 1).padStart(2, "0")}월 ${String(
    d.getDate()
  ).padStart(2, "0")}일`;
}

export function CancelSubscriptionFlow({
  isOpen,
  onClose,
  currentPeriodEnd,
  onCancelSuccess,
}: CancelSubscriptionFlowProps) {
  const [step, setStep] = useState<FlowStep>("form");
  const [reason, setReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [effectiveAt, setEffectiveAt] = useState<string | null>(null);

  const cancelMutation = useCancelSubscription();

  const handleSubmit = useCallback(async () => {
    if (reason.trim().length === 0) return;
    setStep("submitting");
    setErrorMessage(null);
    try {
      const result = await cancelMutation.mutateAsync(reason.trim());
      setEffectiveAt(result.effective_at);
      setStep("done");
      onCancelSuccess?.();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "해지 처리 중 오류가 발생했습니다.";
      setErrorMessage(message);
      setStep("error");
    }
  }, [reason, cancelMutation, onCancelSuccess]);

  const handleRetry = useCallback(() => {
    setStep("form");
    setErrorMessage(null);
  }, []);

  const handleClose = useCallback(() => {
    setReason("");
    setErrorMessage(null);
    setEffectiveAt(null);
    setStep("form");
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  const submitDisabled = reason.trim().length === 0;

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label="구독 해지"
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
            <h2 className={styles.title}>Pro 구독 해지</h2>
            <p className={styles.notice}>
              해지 시 다음 결제일({formatKoreanDate(currentPeriodEnd)})부터
              적용되며 그 전까지 Pro가 유지됩니다.
            </p>
            <div>
              <label className={styles.label} htmlFor="cancel-reason">
                해지 사유를 알려주세요
              </label>
              <textarea
                id="cancel-reason"
                className={styles.textarea}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="서비스 개선에 도움이 됩니다."
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
                disabled={submitDisabled}
              >
                해지하기
              </button>
            </div>
          </div>
        )}

        {step === "submitting" && (
          <div className={styles.content}>
            <div
              className={styles.spinner}
              role="status"
              aria-label="해지 처리 중"
            />
            <p className={styles.statusText}>해지 처리 중...</p>
          </div>
        )}

        {step === "done" && (
          <div className={styles.content}>
            <p className={styles.successIcon}>✓</p>
            <h2 className={styles.title}>해지가 예약되었습니다</h2>
            <p className={styles.notice}>
              {formatKoreanDate(effectiveAt)}부터 적용됩니다.
              그 전까지는 Pro 혜택을 그대로 이용하실 수 있습니다.
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

        {step === "error" && (
          <div className={styles.content}>
            <p className={styles.errorText}>
              {errorMessage || "해지 처리 중 오류가 발생했습니다."}
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

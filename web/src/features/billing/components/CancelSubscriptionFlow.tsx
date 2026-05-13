"use client";

/**
 * CancelSubscriptionFlow — 구독 해지 모달 (Story 3.5 + Story 3.6 v1.1).
 *
 * v1.1: 다이얼로그 진입 시 청약철회 가능 여부를 자동 조회한다(GET /refund-eligibility).
 *   - eligible=true (7일 이내 & 질문 0건) → 라디오로 두 옵션 노출:
 *       ① 일반 해지(다음 결제일에 종료, 사유 필수)
 *       ② 청약철회(즉시 해지 + 전액 환불, 사유 미요 — POST /cancel-with-refund)
 *   - eligible=false → 일반 해지만 노출 + 하단 "환불 사정은 1:1 문의" 안내 카피
 *
 * step 상태:
 *   form           — 옵션 선택 + (일반 해지 선택 시) 사유 textarea
 *   submitting     — spinner
 *   done_canceled  — 일반 해지 예약 완료 ("YYYY-MM-DD부터 적용")
 *   done_refunded  — 청약철회 완료 ("환불이 처리되었습니다")
 *   error          — errorMessage + 다시 시도
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useCancelSubscription } from "../hooks/useCancelSubscription";
import { useCancelWithRefund } from "../hooks/useCancelWithRefund";
import { useRefundEligibility } from "../hooks/useRefundEligibility";
import styles from "./CancelSubscriptionFlow.module.css";

export interface CancelSubscriptionFlowProps {
  isOpen: boolean;
  onClose: () => void;
  /** 적용 예정일(ISO) — 모달 안내 카피에 표시. */
  currentPeriodEnd: string | null;
  onCancelSuccess?: () => void;
}

type FlowStep = "form" | "submitting" | "done_canceled" | "done_refunded" | "error";
type CancelOption = "scheduled" | "cooling_off";

function formatKoreanDate(iso: string | null | undefined): string {
  if (!iso) return "다음 결제일";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "다음 결제일";
  return `${d.getFullYear()}년 ${String(d.getMonth() + 1).padStart(2, "0")}월 ${String(
    d.getDate()
  ).padStart(2, "0")}일`;
}

function formatAmount(amount: number | null): string {
  if (amount == null) return "-";
  return `${amount.toLocaleString("ko-KR")}원`;
}

export function CancelSubscriptionFlow({
  isOpen,
  onClose,
  currentPeriodEnd,
  onCancelSuccess,
}: CancelSubscriptionFlowProps) {
  const [step, setStep] = useState<FlowStep>("form");
  const [option, setOption] = useState<CancelOption>("scheduled");
  const [reason, setReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [effectiveAt, setEffectiveAt] = useState<string | null>(null);
  const [refundedAmount, setRefundedAmount] = useState<number | null>(null);

  const cancelMutation = useCancelSubscription();
  const refundMutation = useCancelWithRefund();
  const { data: eligibility, isLoading: eligibilityLoading } = useRefundEligibility({
    enabled: isOpen,
  });

  const coolingOffAvailable = eligibility?.eligible === true;

  useEffect(() => {
    if (!coolingOffAvailable && option === "cooling_off") {
      setOption("scheduled");
    }
  }, [coolingOffAvailable, option]);

  const handleSubmitScheduled = useCallback(async () => {
    if (reason.trim().length === 0) return;
    setStep("submitting");
    setErrorMessage(null);
    try {
      const result = await cancelMutation.mutateAsync(reason.trim());
      setEffectiveAt(result.effective_at);
      setStep("done_canceled");
      onCancelSuccess?.();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "해지 처리 중 오류가 발생했습니다.";
      setErrorMessage(message);
      setStep("error");
    }
  }, [reason, cancelMutation, onCancelSuccess]);

  const handleSubmitCoolingOff = useCallback(async () => {
    setStep("submitting");
    setErrorMessage(null);
    try {
      const result = await refundMutation.mutateAsync();
      setEffectiveAt(result.refunded_at);
      setRefundedAmount(result.amount_krw);
      setStep("done_refunded");
      onCancelSuccess?.();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "환불 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
      setErrorMessage(message);
      setStep("error");
    }
  }, [refundMutation, onCancelSuccess]);

  const handleSubmit = useCallback(() => {
    if (option === "cooling_off" && coolingOffAvailable) {
      void handleSubmitCoolingOff();
    } else {
      void handleSubmitScheduled();
    }
  }, [option, coolingOffAvailable, handleSubmitCoolingOff, handleSubmitScheduled]);

  const handleRetry = useCallback(() => {
    setStep("form");
    setErrorMessage(null);
  }, []);

  const handleClose = useCallback(() => {
    setReason("");
    setErrorMessage(null);
    setEffectiveAt(null);
    setRefundedAmount(null);
    setOption("scheduled");
    setStep("form");
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  const submitDisabled =
    option === "scheduled"
      ? reason.trim().length === 0
      : !coolingOffAvailable || eligibilityLoading;
  const submitLabel =
    option === "cooling_off" ? "지금 즉시 해지 + 전액 환불" : "해지하기";

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

            {coolingOffAvailable ? (
              <fieldset className={styles.optionGroup}>
                <legend className={styles.label}>해지 방식을 선택해주세요</legend>
                <label className={styles.optionLabel}>
                  <input
                    type="radio"
                    name="cancel-option"
                    value="scheduled"
                    checked={option === "scheduled"}
                    onChange={() => setOption("scheduled")}
                  />
                  <span className={styles.optionBody}>
                    <span className={styles.optionTitle}>
                      다음 결제일까지 이용 후 종료
                    </span>
                    <span className={styles.optionDesc}>
                      {formatKoreanDate(currentPeriodEnd)}부터 적용되며,
                      그 전까지 Pro 혜택을 계속 이용할 수 있습니다.
                    </span>
                  </span>
                </label>
                <label className={styles.optionLabel}>
                  <input
                    type="radio"
                    name="cancel-option"
                    value="cooling_off"
                    checked={option === "cooling_off"}
                    onChange={() => setOption("cooling_off")}
                  />
                  <span className={styles.optionBody}>
                    <span className={styles.optionTitle}>
                      지금 즉시 해지 + 전액 환불
                    </span>
                    <span className={styles.optionDesc}>
                      결제 후 7일 이내 + 아직 질문을 하지 않은 경우 가능합니다.
                      {eligibility?.amount_krw != null && (
                        <>
                          {" "}환불 금액 {formatAmount(eligibility.amount_krw)}이 결제 수단으로 환불됩니다.
                        </>
                      )}
                    </span>
                  </span>
                </label>
              </fieldset>
            ) : (
              <p className={styles.notice}>
                해지 시 다음 결제일({formatKoreanDate(currentPeriodEnd)})부터
                적용되며 그 전까지 Pro가 유지됩니다.
              </p>
            )}

            {option === "scheduled" && (
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
            )}

            {!coolingOffAvailable && !eligibilityLoading && (
              <p className={styles.inquiryHint}>
                환불이 필요하신 경우 사정을{" "}
                <Link href="/my/inquiries/new?type=billing" className={styles.inquiryLink}>
                  1:1 문의
                </Link>
                로 남겨주세요.
              </p>
            )}

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
                {submitLabel}
              </button>
            </div>
          </div>
        )}

        {step === "submitting" && (
          <div className={styles.content}>
            <div
              className={styles.spinner}
              role="status"
              aria-label={
                option === "cooling_off" ? "환불 처리 중" : "해지 처리 중"
              }
            />
            <p className={styles.statusText}>
              {option === "cooling_off"
                ? "환불을 처리하고 있어요…"
                : "해지 처리 중…"}
            </p>
          </div>
        )}

        {step === "done_canceled" && (
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

        {step === "done_refunded" && (
          <div className={styles.content}>
            <p className={styles.successIcon}>✓</p>
            <h2 className={styles.title}>환불이 완료되었습니다</h2>
            <p className={styles.notice}>
              {formatAmount(refundedAmount)}이 결제 수단으로 환불되며,
              구독은 즉시 해지되었습니다. 환불 확정까지 카드사에 따라
              영업일 기준 2~7일이 소요될 수 있습니다.
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
              {errorMessage || "처리 중 오류가 발생했습니다."}
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

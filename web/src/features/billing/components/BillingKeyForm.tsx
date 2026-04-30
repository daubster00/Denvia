"use client";

/**
 * BillingKeyForm — 빌링키 등록 모달.
 * 카드 번호/유효기간/CVC는 토스 결제창에서 처리 — 이 모달에서 직접 수집하지 않음.
 *
 * step 상태:
 *   form        — 초기 상태, "카드 등록하고 Pro 시작하기" 버튼 표시
 *   redirecting — 토스 결제창으로 이동 중
 *   processing  — successUrl 복귀 후 서버 API 호출 중
 *   done        — Pro 활성화 완료
 *   error       — 오류 발생
 */

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import styles from "./BillingKeyForm.module.css";

export interface BillingKeyFormProps {
  isOpen: boolean;
  onClose: () => void;
  /** successUrl 복귀 후 자동 처리 모드 (subscribe 페이지에서 파라미터 감지 후 주입) */
  initialStep?: "form" | "processing";
  onActivationSuccess?: () => void;
  onActivationError?: (message: string) => void;
}

type FormStep = "form" | "redirecting" | "processing" | "done" | "error";

export function BillingKeyForm({
  isOpen,
  onClose,
  initialStep = "form",
  onActivationSuccess,
  onActivationError,
}: BillingKeyFormProps) {
  const router = useRouter();
  const [step, setStep] = useState<FormStep>(initialStep);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleCardRegister = useCallback(async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setStep("redirecting");

    try {
      // 브라우저 전용 동적 import — SSR 시 window 접근 금지 (AR30)
      const { loadTossPayments } = await import("@tosspayments/tosspayments-sdk");
      const clientKey = process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY;
      if (!clientKey) {
        throw new Error("결제 설정이 올바르지 않습니다. 관리자에게 문의해주세요.");
      }

      // crypto.randomUUID() — 자동증가 user id/email/phone 금지 (토스 정책)
      const customerKey = `denvia_${crypto.randomUUID()}`;

      const tossPayments = await loadTossPayments(clientKey);
      const payment = tossPayments.payment({ customerKey });

      await payment.requestBillingAuth({
        method: "CARD",
        successUrl: `${window.location.origin}/subscribe?step=billing_auth_ok`,
        failUrl: `${window.location.origin}/subscribe?step=billing_auth_fail`,
      });
      // 리다이렉트가 발생하므로 이후 코드는 실행되지 않음
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "결제창 초기화에 실패했습니다.";
      setErrorMessage(message);
      setStep("error");
      setIsSubmitting(false);
      onActivationError?.(message);
    }
  }, [isSubmitting, onActivationError]);

  const handleDone = useCallback(() => {
    onActivationSuccess?.();
    router.push("/");
  }, [onActivationSuccess, router]);

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="카드 등록">
      <div className={styles.modal}>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={onClose}
          aria-label="닫기"
        >
          ✕
        </button>

        {step === "form" && (
          <div className={styles.content}>
            <h2 className={styles.title}>Pro 구독 시작</h2>
            <p className={styles.description}>
              카드를 등록하면 즉시 Pro로 전환됩니다.
              <br />
              카드 정보는 토스페이먼츠가 안전하게 처리합니다.
            </p>
            <button
              type="button"
              className={styles.ctaBtn}
              onClick={handleCardRegister}
              disabled={isSubmitting}
            >
              카드 등록하고 Pro 시작하기
            </button>
          </div>
        )}

        {step === "redirecting" && (
          <div className={styles.content}>
            <div className={styles.spinner} role="status" aria-label="결제창 이동 중" />
            <p className={styles.statusText}>토스페이먼츠 결제창으로 이동 중...</p>
          </div>
        )}

        {step === "processing" && (
          <div className={styles.content}>
            <div className={styles.spinner} role="status" aria-label="결제 처리 중" />
            <p className={styles.statusText}>결제 처리 중...</p>
          </div>
        )}

        {step === "done" && (
          <div className={styles.content}>
            <p className={styles.successIcon}>👑</p>
            <h2 className={styles.title}>Pro 구독이 시작되었습니다!</h2>
            <p className={styles.description}>
              이제 무제한으로 임상 Q&A를 이용하실 수 있습니다.
            </p>
            <button type="button" className={styles.ctaBtn} onClick={handleDone}>
              시작하기
            </button>
          </div>
        )}

        {step === "error" && (
          <div className={styles.content}>
            <p className={styles.errorText}>
              {errorMessage || "결제 처리 중 오류가 발생했습니다."}
            </p>
            <button
              type="button"
              className={styles.retryBtn}
              onClick={() => {
                setStep("form");
                setErrorMessage(null);
                setIsSubmitting(false);
              }}
            >
              다시 시도
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** 외부에서 step을 직접 제어할 수 있는 인터페이스 — subscribe 페이지에서 사용. */
export function useBillingKeyFormStep() {
  const [step, setStep] = useState<FormStep>("form");
  return { step, setStep };
}

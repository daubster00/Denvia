"use client";

/**
 * Story 1.7 — ConfirmWithdrawPopup
 *
 * 본인 계정 탈퇴 2단계 확인 팝업.
 * - 자체 가입자(`is_social=false`): 비밀번호 입력 → DELETE /api/v1/me
 * - 소셜 가입자(`is_social=true`): "인증번호 전송" → OTP 입력 → 토큰 → DELETE /api/v1/me
 * - 활성 Pro 구독자는 서버 409 → useAlertStore로 안내
 *
 * 진입점: Epic 4 마이페이지 도입 전까지는 임시 settings 페이지에서 호출.
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/types/api";
import { useSessionStore } from "@/stores/session-store";
import { useAlertStore } from "@/stores/alert-store";
import { useToastStore } from "@/stores/toast-store";

import {
  sendWithdrawOtp,
  verifyWithdrawOtp,
  withdraw,
} from "./api";
import authForm from "@/styles/auth-forms.module.css";
import styles from "./ConfirmWithdrawPopup.module.css";

interface ConfirmWithdrawPopupProps {
  open: boolean;
  onClose: () => void;
}

export function ConfirmWithdrawPopup({ open, onClose }: ConfirmWithdrawPopupProps) {
  const user = useSessionStore((s) => s.user);
  const clearSession = useSessionStore((s) => s.clearSession);
  const showAlert = useAlertStore((s) => s.show);
  const showToast = useToastStore((s) => s.show);
  const router = useRouter();
  const qc = useQueryClient();

  const [acknowledged, setAcknowledged] = useState(false);
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // 소셜 OTP 분기 상태
  const [otpCode, setOtpCode] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [maskedPhone, setMaskedPhone] = useState<string | null>(null);
  const [phoneVerificationToken, setPhoneVerificationToken] = useState<string | null>(null);
  const [otpSending, setOtpSending] = useState(false);
  const [otpVerifying, setOtpVerifying] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  // 팝업이 열릴 때마다 상태 초기화
  useEffect(() => {
    if (open) {
      setAcknowledged(false);
      setPassword("");
      setPasswordError(null);
      setOtpCode("");
      setOtpError(null);
      setMaskedPhone(null);
      setPhoneVerificationToken(null);
      setOtpSending(false);
      setOtpVerifying(false);
      setSubmitting(false);
    }
  }, [open]);

  // ESC 닫힘
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !user) return null;

  const isSocial = user.is_social;
  const canSubmit =
    acknowledged &&
    !submitting &&
    (isSocial
      ? phoneVerificationToken !== null
      : password.length > 0);

  const handleSendOtp = async () => {
    setOtpSending(true);
    setOtpError(null);
    try {
      const res = await sendWithdrawOtp();
      setMaskedPhone(res.masked_phone);
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      setOtpError(apiErr?.message ?? "인증번호 발송에 실패했습니다.");
    } finally {
      setOtpSending(false);
    }
  };

  const handleVerifyOtp = async () => {
    if (otpCode.length === 0) return;
    setOtpVerifying(true);
    setOtpError(null);
    try {
      const res = await verifyWithdrawOtp(otpCode);
      setPhoneVerificationToken(res.phone_verification_token);
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      setOtpError(apiErr?.message ?? "인증번호가 일치하지 않습니다.");
    } finally {
      setOtpVerifying(false);
    }
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setPasswordError(null);
    try {
      await withdraw(
        isSocial
          ? { phone_verification_token: phoneVerificationToken ?? undefined }
          : { password }
      );
      // 성공 — 클라이언트 세션 종료 + 안내 + 랜딩 이동
      clearSession();
      qc.invalidateQueries({ queryKey: ["session"] });
      showToast("탈퇴가 완료되었습니다", 3000);
      onClose();
      router.replace("/");
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      const code = apiErr?.code ?? "";
      if (code === "SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST") {
        showAlert({
          level: "error",
          title: "구독 해지 필요",
          description:
            "구독을 먼저 해지해주세요. 다음 결제일 이후 탈퇴가 가능합니다.",
        });
      } else if (code === "AUTH_INVALID_CREDENTIALS") {
        setPasswordError("비밀번호가 일치하지 않습니다.");
      } else if (code === "SMS_TOKEN_INVALID") {
        setOtpError("휴대폰 인증이 만료되었습니다. 다시 인증해주세요.");
        setPhoneVerificationToken(null);
      } else {
        showAlert({
          level: "error",
          title: "탈퇴에 실패했습니다",
          description: apiErr?.message ?? "잠시 후 다시 시도해주세요.",
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.dimmer} role="presentation">
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="withdraw-heading"
      >
        <h2 id="withdraw-heading" className={styles.heading}>
          정말로 탈퇴하시겠습니까?
        </h2>
        <p className={styles.description}>
          탈퇴 시 개인 식별 정보(이메일·휴대폰·비밀번호)가 즉시 파기되며
          계정은 복구할 수 없습니다.
        </p>

        <label className={styles.acknowledgeRow}>
          <input
            type="checkbox"
            className={styles.acknowledgeCheckbox}
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
          />
          <span className={styles.acknowledgeText}>
            탈퇴 시 결제 기록은 5년간 보관되며 개인 식별자만 즉시 파기됨을
            이해했습니다.
          </span>
        </label>

        {!isSocial && (
          <div>
            <label htmlFor="withdraw-password" className={authForm.fieldLabel}>
              현재 비밀번호
            </label>
            <input
              id="withdraw-password"
              type="password"
              autoComplete="current-password"
              className={
                passwordError
                  ? `${authForm.input} ${authForm.inputError}`
                  : authForm.input
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={!!passwordError}
              aria-describedby={passwordError ? "withdraw-password-error" : undefined}
            />
            {passwordError && (
              <p
                id="withdraw-password-error"
                role="alert"
                className={authForm.fieldError}
              >
                {passwordError}
              </p>
            )}
          </div>
        )}

        {isSocial && (
          <div>
            {!maskedPhone && (
              <button
                type="button"
                className={authForm.smsRequestBtn}
                onClick={handleSendOtp}
                disabled={otpSending}
              >
                {otpSending ? "전송 중..." : "인증번호 전송"}
              </button>
            )}
            {maskedPhone && (
              <>
                <p className={styles.maskedPhone}>
                  인증번호를 {maskedPhone}로 전송했습니다.
                </p>
                <label htmlFor="withdraw-otp" className={authForm.fieldLabel}>
                  인증번호 6자리
                </label>
                <input
                  id="withdraw-otp"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  className={
                    otpError
                      ? `${authForm.input} ${authForm.inputError}`
                      : authForm.input
                  }
                  value={otpCode}
                  onChange={(e) =>
                    setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  disabled={phoneVerificationToken !== null}
                />
                {phoneVerificationToken === null && (
                  <button
                    type="button"
                    className={authForm.smsRequestBtn}
                    onClick={handleVerifyOtp}
                    disabled={otpVerifying || otpCode.length !== 6}
                  >
                    {otpVerifying ? "확인 중..." : "확인"}
                  </button>
                )}
                {phoneVerificationToken !== null && (
                  <p className={authForm.smsVerified}>인증이 완료되었습니다.</p>
                )}
                {otpError && (
                  <p role="alert" className={authForm.fieldError}>
                    {otpError}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={submitting}
          >
            취소
          </button>
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            {submitting ? "처리 중..." : "탈퇴하기"}
          </button>
        </div>
      </div>
    </div>
  );
}

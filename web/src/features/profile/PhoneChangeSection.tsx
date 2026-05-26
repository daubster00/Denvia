"use client";

/**
 * 휴대폰 번호 변경 섹션 — 마이페이지 회원정보 인라인 OTP 흐름.
 *
 * 1) 현재 휴대폰을 표시(편집 가능). 사용자가 다른 번호 입력 → "인증번호 전송" 활성
 * 2) SMS OTP 발송(purpose=phone_change) → SMSCodeInput 표시
 * 3) 코드 입력 완료 → /sms/verify로 phone_verification_token 발급
 * 4) "변경하기" → PATCH /me/profile (phone + token)
 *
 * SignupForm의 OTP 패턴을 거의 그대로 따른다.
 */

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { PhoneNumberField } from "@/features/auth/PhoneNumberField";
import { SMSCodeInput } from "@/features/auth/SMSCodeInput";
import { sendSmsOtp, verifySmsOtp } from "@/features/auth/api";
import { ApiError } from "@/types/api";
import { useToastStore } from "@/stores/toast-store";
import authForm from "@/styles/auth-forms.module.css";

import { updateProfile } from "./api";
import styles from "./PhoneChangeSection.module.css";

interface Props {
  currentPhone: string | null;
}

function normalize(phone: string): string {
  return phone.replace(/\D/g, "");
}

function formatPhone(digits: string | null): string {
  if (!digits) return "";
  const d = digits.replace(/\D/g, "");
  if (d.length <= 3) return d;
  if (d.length <= 7) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

const ERROR_COPY: Record<string, string> = {
  ACCOUNT_PHONE_DUPLICATE: "이미 사용 중인 휴대폰 번호입니다.",
  SMS_TOKEN_INVALID: "휴대폰 인증이 만료되었습니다. 다시 인증해주세요.",
  SMS_COOLDOWN_ACTIVE: "잠시 후 다시 요청해주세요.",
  SMS_MAX_RETRIES_EXCEEDED: "인증번호 발송 한도를 초과했습니다. 1시간 후 다시 시도해주세요.",
  SMS_ANOMALY_BLOCKED:
    "비정상적인 인증 시도가 감지되어 24시간 동안 휴대폰 인증이 제한됩니다. 자동화된 접근으로 의심되는 경우 차단되며, 본인이 맞다면 잠시 후 다시 시도해 주세요.",
  SMS_CODE_INVALID: "인증번호가 일치하지 않습니다.",
  SMS_MAX_WRONG_ATTEMPTS: "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요.",
  SMS_SESSION_EXPIRED: "인증번호가 만료되었습니다. 다시 요청해주세요.",
};

export function PhoneChangeSection({ currentPhone }: Props) {
  const showToast = useToastStore((s) => s.show);
  const qc = useQueryClient();

  const [phoneInput, setPhoneInput] = useState(formatPhone(currentPhone));
  const [smsRequested, setSmsRequested] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [otpError, setOtpError] = useState<string | undefined>(undefined);
  const [saving, setSaving] = useState(false);

  const normalized = normalize(phoneInput);
  const currentNormalized = normalize(currentPhone ?? "");
  const isPhoneChanged = normalized !== currentNormalized;
  const isValidPhone = /^010\d{8}$/.test(normalized);

  const resetVerification = useCallback(() => {
    setSmsRequested(false);
    setToken(null);
    setDebugCode(null);
    setOtpError(undefined);
  }, []);

  const handlePhoneChange = (v: string) => {
    setPhoneInput(v);
    // 휴대폰을 다시 바꾸면 이미 받은 토큰은 무효화
    resetVerification();
  };

  const handleSendOtp = useCallback(async () => {
    setOtpError(undefined);
    try {
      const res = await sendSmsOtp(normalized, "phone_change");
      setDebugCode(res.debug_code ?? null);
      setSmsRequested(true);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      setOtpError(ERROR_COPY[code] ?? "인증번호 발송에 실패했습니다.");
    }
  }, [normalized]);

  const handleOtpComplete = useCallback(
    async (otpCode: string) => {
      setOtpError(undefined);
      try {
        const res = await verifySmsOtp(normalized, otpCode, "phone_change");
        setToken(res.phone_verification_token);
      } catch (e) {
        const code = e instanceof ApiError ? e.code : "";
        setOtpError(ERROR_COPY[code] ?? "인증에 실패했습니다.");
      }
    },
    [normalized]
  );

  const handleSave = async () => {
    if (!token) return;
    setSaving(true);
    setOtpError(undefined);
    try {
      await updateProfile({ phone: normalized, phone_verification_token: token });
      showToast("휴대폰 번호가 변경되었습니다.", 3000);
      qc.invalidateQueries({ queryKey: ["profile"] });
      resetVerification();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      setOtpError(ERROR_COPY[code] ?? "변경에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.row}>
        <div className={styles.phoneCol}>
          <PhoneNumberField
            id="profile-phone"
            value={phoneInput}
            onChange={handlePhoneChange}
            error={otpError && !smsRequested ? otpError : undefined}
          />
        </div>
        {!smsRequested && (
          <button
            type="button"
            className={styles.actionBtn}
            onClick={handleSendOtp}
            disabled={!isPhoneChanged || !isValidPhone}
          >
            인증번호 전송
          </button>
        )}
        {smsRequested && token && (
          <button
            type="button"
            className={styles.savingBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "변경 중..." : "변경하기"}
          </button>
        )}
      </div>

      {smsRequested && (
        <div>
          <p className={styles.help}>
            새 휴대폰으로 전송된 6자리 인증번호를 입력하세요.
          </p>
          {debugCode && (
            <p className={styles.debugCode}>인증번호(dev): {debugCode}</p>
          )}
          <SMSCodeInput
            onComplete={handleOtpComplete}
            onResend={handleSendOtp}
            error={otpError}
            disabled={token !== null}
          />
          {token && <p className={styles.verified}>✓ 인증이 완료되었습니다.</p>}
        </div>
      )}

      {!isPhoneChanged && currentPhone && (
        <p className={styles.help}>현재 번호: {formatPhone(currentPhone)}</p>
      )}

      {/* 인증되지 않은 상태에서의 에러는 PhoneNumberField 아래 표시되지만,
          smsRequested 이후 발생한 일반 에러는 위 SMSCodeInput error 경로로 표시됨. */}
      {otpError && smsRequested && !token && (
        <p role="alert" className={authForm.fieldError}>
          {otpError}
        </p>
      )}
    </div>
  );
}

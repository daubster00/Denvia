"use client";

import { useState, useCallback } from "react";
import { sendSmsOtp, verifySmsOtp, lookupId } from "./api";
import { PhoneNumberField } from "./PhoneNumberField";
import { SMSCodeInput } from "./SMSCodeInput";
import authStyles from "@/styles/auth-forms.module.css";
import styles from "@/styles/find-id.module.css";

interface FindIdPopupProps {
  onBack: () => void;
}

type Step = "phone" | "otp" | "result";

interface LookupResult {
  email_masked: string | null;
  signup_method: "email" | "kakao" | "google" | "naver" | "social" | null;
}

const PROVIDER_LABELS: Record<"kakao" | "google" | "naver", string> = {
  kakao: "카카오",
  google: "구글",
  naver: "네이버",
};

/** 아이디 찾기 — 3단계: 휴대폰 입력 → OTP 검증 → 결과 표시 */
export function FindIdPopup({ onBack }: FindIdPopupProps) {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | undefined>();
  const [cooldownSeconds, setCooldownSeconds] = useState(60);
  const [otpError, setOtpError] = useState<string | undefined>();
  const [result, setResult] = useState<LookupResult | null>(null);
  const [sendingOtp, setSendingOtp] = useState(false);
  const [debugSmsCode, setDebugSmsCode] = useState<string | null>(null);

  const normalizedPhone = phone.replace(/\D/g, "");

  const handleSendOtp = async () => {
    if (!/^010\d{8}$/.test(normalizedPhone)) {
      setPhoneError("올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)");
      return;
    }
    setPhoneError(undefined);
    setSendingOtp(true);
    try {
      const res = await sendSmsOtp(normalizedPhone, "find_id");
      setCooldownSeconds(res.cooldown_seconds);
      setDebugSmsCode(res.debug_code ?? null);
      setStep("otp");
    } catch {
      setPhoneError("인증번호 전송에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setSendingOtp(false);
    }
  };

  const handleResendOtp = useCallback(async () => {
    const res = await sendSmsOtp(normalizedPhone, "find_id");
    setDebugSmsCode(res.debug_code ?? null);
  }, [normalizedPhone]);

  const handleOtpComplete = async (code: string) => {
    setOtpError(undefined);
    try {
      const { phone_verification_token } = await verifySmsOtp(normalizedPhone, code, "find_id");
      const lookupResult = await lookupId({ phone_verification_token });
      setResult(lookupResult);
      setStep("result");
    } catch {
      setOtpError("인증번호가 올바르지 않습니다.");
    }
  };

  if (step === "phone") {
    return (
      <div className={styles.column}>
        <PhoneNumberField
          id="find-id-phone"
          value={phone}
          onChange={setPhone}
          error={phoneError}
          autoFocus
        />
        <button
          type="button"
          onClick={handleSendOtp}
          disabled={sendingOtp}
          aria-busy={sendingOtp}
          className={`${authStyles.primaryBtn} ${sendingOtp ? authStyles.primaryBtnLoading : ""}`}
        >
          {sendingOtp ? "전송 중..." : "인증번호 전송"}
        </button>
      </div>
    );
  }

  if (step === "otp") {
    return (
      <div className={styles.column}>
        <p className={styles.otpHelper}>
          {phone}으로 인증번호를 전송했습니다.
        </p>
        {debugSmsCode && (
          <p className={styles.otpHelper}>인증번호: {debugSmsCode}</p>
        )}
        <SMSCodeInput
          onComplete={handleOtpComplete}
          onResend={handleResendOtp}
          cooldownSeconds={cooldownSeconds}
          error={otpError}
        />
      </div>
    );
  }

  // 결과 화면
  const getResultMessage = () => {
    if (!result) return null;
    if (result.email_masked && result.signup_method === "email") {
      return (
        <>
          <p className={styles.resultLabel}>가입 이메일</p>
          <p className={styles.resultEmail}>{result.email_masked}</p>
          <p className={styles.resultHint}>이메일로 로그인해주세요.</p>
        </>
      );
    }
    if (
      result.signup_method === "kakao" ||
      result.signup_method === "google" ||
      result.signup_method === "naver"
    ) {
      const label = PROVIDER_LABELS[result.signup_method];
      return (
        <p className={styles.resultBody}>
          이 휴대폰은 {label} 계정으로 가입되어 있습니다.
          <br />
          {label} 로그인을 이용해주세요.
        </p>
      );
    }
    if (result.signup_method === "social") {
      return (
        <p className={styles.resultBody}>
          이 휴대폰은 소셜 계정으로 가입되어 있습니다.
          <br />
          소셜 로그인을 이용해주세요.
        </p>
      );
    }
    return (
      <p className={styles.resultEmpty}>
        해당 휴대폰으로 가입된 계정이 없거나 소셜 가입일 수 있습니다.
      </p>
    );
  };

  return (
    <div className={styles.columnCentered}>
      {getResultMessage()}
      <button
        type="button"
        onClick={onBack}
        className={`${authStyles.primaryBtn} ${styles.backBtn}`}
      >
        로그인 화면으로 돌아가기
      </button>
    </div>
  );
}

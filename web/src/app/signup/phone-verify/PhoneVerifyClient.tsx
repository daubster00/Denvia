"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { Typography } from "@wanteddev/wds";

import {
  completeOAuthSignup,
  sendSmsOtp,
  verifySmsOtp,
} from "@/features/auth/api";
import { PhoneNumberField } from "@/features/auth/PhoneNumberField";
import { SMSCodeInput } from "@/features/auth/SMSCodeInput";
import { ApiError } from "@/types/api";
import { getErrorMessage } from "@/lib/error-copy";

type Step = "phone" | "sms";

function normalizePhone(p: string): string {
  return p.replace(/\D/g, "");
}

// server 에러 코드 중 pending 세션 자체가 만료/무효 → `/`로 리다이렉트해야 하는 코드
const PENDING_FATAL_CODES = new Set([
  "OAUTH_PENDING_EXPIRED",
  "OAUTH_PENDING_INVALID",
  "OAUTH_STATE_INVALID",
]);

export function PhoneVerifyClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  // 초기 1회만 token을 읽어 이후 history.replaceState로 URL에서 제거해도 유지.
  const tokenRef = useRef<string | null>(null);
  if (tokenRef.current === null) {
    const raw = searchParams?.get("token") ?? "";
    tokenRef.current = raw.trim() || null;
  }
  const token = tokenRef.current;

  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  // OTP 검증 성공 시 잠긴 phone — 이후 사용자가 phone 필드를 수정해도 완료 시 전송되는 번호는 이 값.
  const [verifiedPhone, setVerifiedPhone] = useState<string | null>(null);
  const [phoneVerificationToken, setPhoneVerificationToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sending, setSending] = useState(false);
  const smsBoxRef = useRef<HTMLDivElement>(null);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // token 누락 시 즉시 리다이렉트 + 존재 시 URL에서 token 쿼리 제거 (Referer/history 유출 방지)
  useEffect(() => {
    if (!token) {
      router.replace("/?oauth_error=OAUTH_PENDING_EXPIRED");
      return;
    }
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (url.searchParams.has("token")) {
        url.searchParams.delete("token");
        window.history.replaceState({}, "", url.pathname + (url.search || ""));
      }
    }
  }, [token, router]);

  // OTP 단계 진입 시 SMS 입력 영역으로 스크롤·포커스
  useEffect(() => {
    if (step === "sms") {
      const input = smsBoxRef.current?.querySelector<HTMLInputElement>(
        'input[aria-label^="인증번호"]'
      );
      input?.focus();
    }
  }, [step]);

  const handlePendingFatalRedirect = useCallback(
    (code: string) => {
      router.replace(`/?oauth_error=${encodeURIComponent(code)}`);
    },
    [router]
  );

  const handleSendOtp = useCallback(async () => {
    if (sending) return;
    setError(null);
    if (!/^010[-\s]?\d{4}[-\s]?\d{4}$/.test(phone)) {
      setError("올바른 휴대폰 번호를 입력하세요.");
      return;
    }
    setSending(true);
    try {
      await sendSmsOtp(normalizePhone(phone), "signup");
      if (!isMountedRef.current) return;
      setStep("sms");
    } catch (e) {
      if (!isMountedRef.current) return;
      if (e instanceof ApiError && PENDING_FATAL_CODES.has(e.code)) {
        handlePendingFatalRedirect(e.code);
        return;
      }
      setError(e instanceof ApiError ? getErrorMessage(e.code) : "오류가 발생했습니다.");
    } finally {
      if (isMountedRef.current) setSending(false);
    }
  }, [phone, sending, handlePendingFatalRedirect]);

  const handleOtpComplete = useCallback(
    async (code: string) => {
      setError(null);
      try {
        const res = await verifySmsOtp(normalizePhone(phone), code, "signup");
        if (!isMountedRef.current) return;
        if (!res?.phone_verification_token) {
          setError("인증 응답이 올바르지 않습니다. 인증번호를 다시 요청해주세요.");
          return;
        }
        setPhoneVerificationToken(res.phone_verification_token);
        setVerifiedPhone(normalizePhone(phone));
      } catch (e) {
        if (!isMountedRef.current) return;
        if (e instanceof ApiError && PENDING_FATAL_CODES.has(e.code)) {
          handlePendingFatalRedirect(e.code);
          return;
        }
        setError(e instanceof ApiError ? getErrorMessage(e.code) : "오류가 발생했습니다.");
      }
    },
    [phone, handlePendingFatalRedirect]
  );

  const handleResendOtp = useCallback(async () => {
    await sendSmsOtp(normalizePhone(phone), "signup");
  }, [phone]);

  const handleComplete = useCallback(async () => {
    if (submitting) return;
    if (!token || !phoneVerificationToken || !verifiedPhone) return;
    setSubmitting(true);
    setError(null);
    try {
      await completeOAuthSignup({
        signup_pending_token: token,
        phone: verifiedPhone,
        phone_verification_token: phoneVerificationToken,
      });
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      if (!isMountedRef.current) return;
      // AC-7: phone collision 외 성공 경로 — push로 /signup/segment 이동 (기존 히스토리 유지)
      router.push("/signup/segment");
    } catch (e) {
      if (!isMountedRef.current) return;
      if (e instanceof ApiError) {
        // AC-7: OAUTH_PHONE_COLLISION 은 홈으로 push (spec Task 7.1)
        // OAUTH_PENDING_INVALID 등 pending 세션 만료는 replace로 재진입 차단
        if (e.code === "OAUTH_PHONE_COLLISION") {
          router.push(`/?oauth_error=${encodeURIComponent(e.code)}`);
          return;
        }
        if (PENDING_FATAL_CODES.has(e.code)) {
          handlePendingFatalRedirect(e.code);
          return;
        }
        setError(getErrorMessage(e.code));
      } else {
        setError("오류가 발생했습니다.");
      }
    } finally {
      if (isMountedRef.current) setSubmitting(false);
    }
  }, [
    token,
    phoneVerificationToken,
    verifiedPhone,
    queryClient,
    router,
    submitting,
    handlePendingFatalRedirect,
  ]);

  // token 없는 초기 렌더는 빈 레이아웃(보이지 않음)만 출력 → FOUC 방지 + 즉시 리다이렉트.
  if (!token) {
    return (
      <div
        aria-hidden="true"
        style={{ minHeight: "100vh", background: "#FAFAFA" }}
      />
    );
  }

  const sendOtpDisabled = sending;
  const completeEnabled = Boolean(phoneVerificationToken) && !submitting;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 16px",
        background: "#FAFAFA",
      }}
    >
      <div
        style={{
          width: "min(420px, 100%)",
          background: "#fff",
          borderRadius: 16,
          boxShadow: "0 4px 24px rgba(0,0,0,0.10)",
          padding: "32px 28px",
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Typography
            as="h1"
            variant="heading1"
            weight="bold"
            color="semantic.label.normal"
          >
            휴대폰 인증
          </Typography>
          <Typography
            as="p"
            variant="body2-reading"
            color="semantic.label.alternative"
          >
            소셜 계정에서 휴대폰 정보를 받지 못했습니다. 휴대폰 인증으로 가입을 마무리해주세요.
          </Typography>
        </div>

        <PhoneNumberField value={phone} onChange={setPhone} />

        {step === "phone" ? (
          <button
            type="button"
            onClick={handleSendOtp}
            disabled={sendOtpDisabled}
            aria-busy={sending}
            aria-disabled={sendOtpDisabled}
            style={{
              width: "100%",
              padding: "13px 0",
              border: "none",
              borderRadius: 8,
              background: sendOtpDisabled
                ? "#E1E2E4"
                : "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
              color: sendOtpDisabled ? "#AEB0B6" : "#fff",
              fontSize: 15,
              fontWeight: 600,
              cursor: sendOtpDisabled ? "not-allowed" : "pointer",
            }}
          >
            {sending ? "전송 중..." : "인증번호 받기"}
          </button>
        ) : (
          <div ref={smsBoxRef} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <SMSCodeInput onComplete={handleOtpComplete} onResend={handleResendOtp} />
            <button
              type="button"
              disabled={!completeEnabled}
              aria-busy={submitting}
              aria-disabled={!completeEnabled}
              onClick={handleComplete}
              style={{
                width: "100%",
                padding: "13px 0",
                border: "none",
                borderRadius: 8,
                background: completeEnabled
                  ? "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)"
                  : "#E1E2E4",
                color: completeEnabled ? "#fff" : "#AEB0B6",
                fontSize: 15,
                fontWeight: 600,
                cursor: completeEnabled ? "pointer" : "not-allowed",
              }}
            >
              {submitting ? "가입 중..." : "가입 완료"}
            </button>
          </div>
        )}

        {error && (
          <Typography
            as="p"
            role="alert"
            variant="label1-reading"
            color="semantic.status.negative"
          >
            {error}
          </Typography>
        )}
      </div>
    </div>
  );
}

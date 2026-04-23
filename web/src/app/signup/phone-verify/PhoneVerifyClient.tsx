"use client";

import { useCallback, useEffect, useState } from "react";
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

export function PhoneVerifyClient() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [phoneVerificationToken, setPhoneVerificationToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // token 누락 시 즉시 리다이렉트
  useEffect(() => {
    if (!token) {
      router.replace("/?oauth_error=OAUTH_PENDING_EXPIRED");
    }
  }, [token, router]);

  const handleSendOtp = useCallback(async () => {
    setError(null);
    if (!/^010[-\s]?\d{4}[-\s]?\d{4}$/.test(phone)) {
      setError("올바른 휴대폰 번호를 입력하세요.");
      return;
    }
    try {
      await sendSmsOtp(normalizePhone(phone), "signup");
      setStep("sms");
    } catch (e) {
      setError(e instanceof ApiError ? (getErrorMessage(e.code) || e.message) : "오류가 발생했습니다.");
    }
  }, [phone]);

  const handleOtpComplete = useCallback(
    async (code: string) => {
      setError(null);
      try {
        const res = await verifySmsOtp(normalizePhone(phone), code, "signup");
        setPhoneVerificationToken(res.phone_verification_token);
      } catch (e) {
        setError(e instanceof ApiError ? (getErrorMessage(e.code) || e.message) : "오류가 발생했습니다.");
      }
    },
    [phone]
  );

  const handleResendOtp = useCallback(async () => {
    await sendSmsOtp(normalizePhone(phone), "signup");
  }, [phone]);

  const handleComplete = useCallback(async () => {
    if (!token || !phoneVerificationToken) return;
    setSubmitting(true);
    setError(null);
    try {
      await completeOAuthSignup({
        signup_pending_token: token,
        phone: normalizePhone(phone),
        phone_verification_token: phoneVerificationToken,
      });
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      router.push("/signup/segment");
    } catch (e) {
      if (e instanceof ApiError) {
        const msg = getErrorMessage(e.code) || e.message;
        if (e.code === "OAUTH_PHONE_COLLISION" || e.code === "OAUTH_PENDING_INVALID") {
          router.replace(`/?oauth_error=${e.code}`);
          return;
        }
        setError(msg);
      } else {
        setError("오류가 발생했습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  }, [token, phoneVerificationToken, phone, queryClient, router]);

  if (!token) return null;

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
            style={{
              width: "100%",
              padding: "13px 0",
              border: "none",
              borderRadius: 8,
              background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
              color: "#fff",
              fontSize: 15,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            인증번호 받기
          </button>
        ) : (
          <>
            <SMSCodeInput onComplete={handleOtpComplete} onResend={handleResendOtp} />
            <button
              type="button"
              disabled={!phoneVerificationToken || submitting}
              onClick={handleComplete}
              style={{
                width: "100%",
                padding: "13px 0",
                border: "none",
                borderRadius: 8,
                background: phoneVerificationToken
                  ? "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)"
                  : "#E1E2E4",
                color: phoneVerificationToken ? "#fff" : "#AEB0B6",
                fontSize: 15,
                fontWeight: 600,
                cursor: phoneVerificationToken ? "pointer" : "default",
              }}
            >
              {submitting ? "가입 중..." : "가입 완료"}
            </button>
          </>
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

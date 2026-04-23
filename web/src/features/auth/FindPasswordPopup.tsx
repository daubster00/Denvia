"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { requestPasswordReset } from "./api";
import { PhoneNumberField } from "./PhoneNumberField";

const emailOnlySchema = z.object({
  email: z.string().email("올바른 이메일을 입력하세요."),
});
type EmailOnlyValues = z.infer<typeof emailOnlySchema>;

const phoneRegex = /^010[-\s]?\d{4}[-\s]?\d{4}$/;

interface FindPasswordPopupProps {
  onBack: () => void;
}

/** 비밀번호 찾기 폼 — 이메일 + 휴대폰 입력 후 SMS 임시 비밀번호 발송 */
export function FindPasswordPopup({ onBack }: FindPasswordPopupProps) {
  const [submitted, setSubmitted] = useState(false);
  const [phoneValue, setPhoneValue] = useState("");
  const [phoneError, setPhoneError] = useState<string | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<EmailOnlyValues>({
    resolver: zodResolver(emailOnlySchema),
  });

  const onSubmit = async (data: EmailOnlyValues) => {
    // 휴대폰 번호 검증
    if (!phoneRegex.test(phoneValue)) {
      setPhoneError("올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)");
      return;
    }
    setPhoneError(undefined);
    setIsSubmitting(true);
    try {
      const normalizedPhone = phoneValue.replace(/\D/g, "");
      await requestPasswordReset({ email: data.email, phone: normalizedPhone });
    } catch {
      // UX Spec §1011: 계정 열거 방지 — 오류 여부와 무관하게 동일 성공 메시지
    } finally {
      setIsSubmitting(false);
      setSubmitted(true);
    }
  };

  if (submitted) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16, textAlign: "center", padding: "8px 0" }}>
        <p style={{ margin: 0, fontSize: 15, color: "#171719", lineHeight: 1.6 }}>
          등록된 휴대폰으로 임시 비밀번호를 보내드렸습니다. SMS를 확인해주세요.
        </p>
        <button
          type="button"
          onClick={onBack}
          style={{
            padding: "12px 0",
            background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            fontSize: 15,
            fontWeight: 600,
            cursor: "pointer",
            marginTop: 8,
          }}
        >
          로그인 화면으로 돌아가기
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <label htmlFor="find-pw-email" style={{ display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
          이메일 <span aria-label="필수" style={{ color: "#7C3AED" }}>*</span>
        </label>
        <input
          id="find-pw-email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "find-pw-email-error" : undefined}
          style={{
            width: "100%",
            padding: "10px 12px",
            border: `1px solid ${errors.email ? "#EF4444" : "#E1E2E4"}`,
            borderRadius: 8,
            fontSize: 14,
            outline: "none",
            boxSizing: "border-box",
          }}
          {...register("email")}
        />
        {errors.email && (
          <p id="find-pw-email-error" role="alert" style={{ color: "#EF4444", fontSize: 12, marginTop: 4 }}>
            {errors.email.message}
          </p>
        )}
      </div>

      <PhoneNumberField
        id="find-pw-phone"
        value={phoneValue}
        onChange={setPhoneValue}
        error={phoneError}
      />

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        style={{
          padding: "12px 0",
          background: isSubmitting ? "#C4B5FD" : "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
          color: "#fff",
          border: "none",
          borderRadius: 8,
          fontSize: 15,
          fontWeight: 600,
          cursor: isSubmitting ? "not-allowed" : "pointer",
          marginTop: 4,
        }}
      >
        {isSubmitting ? "전송 중..." : "임시 비밀번호 받기"}
      </button>
    </form>
  );
}

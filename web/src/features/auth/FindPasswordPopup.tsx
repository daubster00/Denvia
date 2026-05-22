"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { requestPasswordReset } from "./api";
import { PhoneNumberField } from "./PhoneNumberField";
import { useSessionStore } from "@/stores/session-store";
import styles from "@/styles/auth-forms.module.css";

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
  const setForcePasswordReset = useSessionStore((s) => s.setForcePasswordReset);

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
      // 2차 escalation 강제 모드 해제 — 임시 비번이 발송된 시점부터 로그인 락이 풀려
      // 사용자가 받은 임시 비번으로 다시 정상 로그인할 수 있음.
      setForcePasswordReset(false);
    }
  };

  if (submitted) {
    return (
      <div className={styles.successPanel}>
        <p className={styles.successText}>
          등록된 휴대폰으로 임시 비밀번호를 보내드렸습니다. SMS를 확인해주세요.
        </p>
        <button type="button" onClick={onBack} className={styles.backBtn}>
          로그인 화면으로 돌아가기
        </button>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className={styles.formColumn}
    >
      <div>
        <label htmlFor="find-pw-email" className={styles.fieldLabel}>
          이메일 <span aria-label="필수" className={styles.required}>*</span>
        </label>
        <input
          id="find-pw-email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "find-pw-email-error" : undefined}
          className={
            errors.email
              ? `${styles.input} ${styles.inputError}`
              : styles.input
          }
          {...register("email")}
        />
        {errors.email && (
          <p id="find-pw-email-error" role="alert" className={styles.fieldError}>
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
        className={
          isSubmitting
            ? `${styles.primaryBtn} ${styles.primaryBtnLoading}`
            : styles.primaryBtn
        }
      >
        {isSubmitting ? "전송 중..." : "임시 비밀번호 받기"}
      </button>
    </form>
  );
}

"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { requestPasswordReset, type FindPasswordProvider } from "./api";
import { PhoneNumberField } from "./PhoneNumberField";
import { useSessionStore } from "@/stores/session-store";
import styles from "@/styles/auth-forms.module.css";
import hintStyles from "./OAuthOnlyHint.module.css";
import popupStyles from "@/styles/login-popup.module.css";
import { KakaoIcon, NaverIcon, GoogleIcon } from "./icons";

const emailOnlySchema = z.object({
  email: z.string().email("올바른 이메일을 입력하세요."),
});
type EmailOnlyValues = z.infer<typeof emailOnlySchema>;

const phoneRegex = /^010[-\s]?\d{4}[-\s]?\d{4}$/;

const PROVIDER_LABEL: Record<FindPasswordProvider, string> = {
  kakao: "카카오",
  google: "구글",
  naver: "네이버",
};

const PROVIDER_BTN_CLASS: Record<FindPasswordProvider, string> = {
  kakao: popupStyles.socialBtnKakao,
  google: popupStyles.socialBtnGoogle,
  naver: popupStyles.socialBtnNaver,
};

interface FindPasswordPopupProps {
  onBack: () => void;
}

type SubmittedState =
  | { kind: "default" }
  | { kind: "social"; providers: FindPasswordProvider[] };

/** 비밀번호 찾기 폼 — 이메일 + 휴대폰 입력 후 SMS 임시 비밀번호 발송.
 *
 * 소셜 전용 가입자(password_hash=NULL)는 SMS가 발송되지 않으므로,
 * 서버가 응답에 담아 보낸 `linked_providers`로 안내 + 해당 소셜 로그인 버튼을 노출한다.
 */
export function FindPasswordPopup({ onBack }: FindPasswordPopupProps) {
  const [submitted, setSubmitted] = useState<SubmittedState | null>(null);
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

  const handleProviderLogin = (provider: FindPasswordProvider) => {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const params = new URLSearchParams({ mode: "login" });
    window.location.href = `${apiBase}/api/v1/auth/oauth/${provider}/authorize?${params}`;
  };

  const onSubmit = async (data: EmailOnlyValues) => {
    // 휴대폰 번호 검증
    if (!phoneRegex.test(phoneValue)) {
      setPhoneError("올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)");
      return;
    }
    setPhoneError(undefined);
    setIsSubmitting(true);

    let next: SubmittedState = { kind: "default" };
    try {
      const normalizedPhone = phoneValue.replace(/\D/g, "");
      const res = await requestPasswordReset({ email: data.email, phone: normalizedPhone });
      if (Array.isArray(res?.linked_providers) && res.linked_providers.length > 0) {
        next = { kind: "social", providers: res.linked_providers };
      }
    } catch {
      // UX Spec §1011: 계정 열거 방지 — 오류 여부와 무관하게 동일 성공 메시지
    } finally {
      setIsSubmitting(false);
      setSubmitted(next);
      // 2차 escalation 강제 모드 해제 — 임시 비번이 발송된 시점부터 로그인 락이 풀려
      // 사용자가 받은 임시 비번으로 다시 정상 로그인할 수 있음.
      setForcePasswordReset(false);
    }
  };

  if (submitted?.kind === "social") {
    const providerLabels = submitted.providers
      .map((p) => PROVIDER_LABEL[p])
      .join(" / ");
    return (
      <div className={styles.successPanel}>
        <p className={styles.successText}>
          {providerLabels}(으)로 가입하신 계정입니다.
          <br />
          별도의 비밀번호가 없어 임시 비밀번호를 발송할 수 없습니다. 아래 버튼으로 다시 로그인해 주세요.
        </p>
        <div className={hintStyles.oauthOnlyHint}>
          <div className={hintStyles.providerButtonRow}>
            {submitted.providers.map((provider) => (
              <button
                key={provider}
                type="button"
                onClick={() => handleProviderLogin(provider)}
                aria-label={`${PROVIDER_LABEL[provider]}로 로그인`}
                className={`${popupStyles.socialBtn} ${PROVIDER_BTN_CLASS[provider]} ${hintStyles.emphasizedPulse}`}
              >
                <span className={popupStyles.socialIcon}>
                  {provider === "kakao" ? (
                    <KakaoIcon />
                  ) : provider === "naver" ? (
                    <NaverIcon />
                  ) : (
                    <GoogleIcon />
                  )}
                </span>
                <span className={popupStyles.socialLabel}>{PROVIDER_LABEL[provider]}로 로그인</span>
                <span className={popupStyles.socialSpacer} aria-hidden="true" />
              </button>
            ))}
          </div>
        </div>
        <button type="button" onClick={onBack} className={styles.backBtn}>
          로그인 화면으로 돌아가기
        </button>
      </div>
    );
  }

  if (submitted?.kind === "default") {
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

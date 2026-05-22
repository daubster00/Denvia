"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, type LoginFormValues } from "./schemas";
import { useSessionStore } from "@/stores/session-store";
import { login } from "./api";
import { ApiError } from "@/types/api";
import styles from "@/styles/auth-forms.module.css";
import hintStyles from "./OAuthOnlyHint.module.css";
import popupStyles from "@/styles/login-popup.module.css";
import { KakaoIcon, NaverIcon, GoogleIcon } from "./icons";

interface EmailLoginTabProps {
  onSignup?: () => void;
  onFindPassword?: () => void;
  onFindId?: () => void;
}

type OAuthProvider = "kakao" | "google" | "naver";

interface OAuthOnlyHintState {
  providers: OAuthProvider[];
  message: string;
}

const VALID_PROVIDERS = new Set<string>(["kakao", "google", "naver"]);

const PROVIDER_LABEL: Record<OAuthProvider, string> = {
  kakao: "카카오",
  google: "구글",
  naver: "네이버",
};

const PROVIDER_BTN_CLASS: Record<OAuthProvider, string> = {
  kakao: popupStyles.socialBtnKakao,
  google: popupStyles.socialBtnGoogle,
  naver: popupStyles.socialBtnNaver,
};

/** 이메일 로그인 탭 — 폼 UI + preferPersist 체크박스 + submit 처리. */
export function EmailLoginTab({ onSignup, onFindPassword, onFindId }: EmailLoginTabProps = {}) {
  const setPreferPersist = useSessionStore((s) => s.setPreferPersist);
  const preferPersist = useSessionStore((s) => s.preferPersist);
  const setUser = useSessionStore((s) => s.setUser);
  const closePopup = useSessionStore((s) => s.closePopup);
  const setForcePasswordReset = useSessionStore((s) => s.setForcePasswordReset);
  const [serverError, setServerError] = useState<string | null>(null);
  const [oauthOnlyHint, setOauthOnlyHint] = useState<OAuthOnlyHintState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const handleProviderLogin = (provider: OAuthProvider) => {
    const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const params = new URLSearchParams({ mode: "login" });
    window.location.href = `${apiBase}/api/v1/auth/oauth/${provider}/authorize?${params}`;
  };

  const onSubmit = async (data: LoginFormValues) => {
    setServerError(null);
    setOauthOnlyHint(null);
    setIsSubmitting(true);
    try {
      const user = await login({
        email: data.email,
        password: data.password,
        persist_session: preferPersist,
      });
      setUser(user);
      closePopup();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === "AUTH_MUST_RESET_PASSWORD") {
          // 2차 escalation — 안내 후 확인 누르면 비번찾기 강제 모드 진입.
          setOauthOnlyHint(null);
          setServerError(null);
          if (typeof window !== "undefined") {
            window.alert(
              "비밀번호 오류가 반복되어 더 이상 로그인할 수 없습니다.\n비밀번호 찾기로 비밀번호를 재설정해 주세요."
            );
          }
          setForcePasswordReset(true);
          onFindPassword?.();
        } else if (err.code === "ACCOUNT_BLOCKED") {
          // 관리자에 의해 차단된 계정. 세션을 발급하지 않고 안내 후 팝업을 닫는다.
          setOauthOnlyHint(null);
          setServerError(null);
          if (typeof window !== "undefined") {
            window.alert(
              err.message || "차단된 계정입니다. 관리자에게 문의하세요.",
            );
          }
          setUser(null);
          closePopup();
        } else if (err.code === "AUTH_TEMPORARILY_LOCKED" || err.code === "RATE_LIMITED") {
          setServerError(err.message || "비밀번호 오류가 반복되어 10분간 로그인이 잠겼습니다. 잠시 후 다시 시도하거나 비밀번호 찾기를 이용하세요.");
          setOauthOnlyHint(null);
        } else if (
          err.code === "AUTH_ACCOUNT_OAUTH_ONLY" &&
          Array.isArray((err.details as { linked_providers?: unknown })?.linked_providers)
        ) {
          const providers = (
            (err.details as { linked_providers: string[] }).linked_providers
          ).filter((p): p is OAuthProvider => VALID_PROVIDERS.has(p));
          setOauthOnlyHint({ providers, message: err.message });
          setServerError(null);
        } else {
          setServerError("이메일 또는 비밀번호가 일치하지 않습니다.");
          setOauthOnlyHint(null);
        }
      } else {
        setServerError("이메일 또는 비밀번호가 일치하지 않습니다.");
        setOauthOnlyHint(null);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className={styles.formColumn}>
      {serverError && (
        <p role="alert" aria-live="assertive" className={styles.serverErrorBanner}>
          {serverError}
        </p>
      )}
      <div>
        <label htmlFor="login-email" className={styles.fieldLabel}>
          이메일 <span aria-label="필수" className={styles.required}>*</span>
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "login-email-error" : undefined}
          className={`${styles.input} ${errors.email ? styles.inputError : ""}`}
          {...register("email")}
        />
        {errors.email && (
          <p id="login-email-error" role="alert" className={styles.fieldError}>
            {errors.email.message}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="login-password" className={styles.fieldLabel}>
          비밀번호 <span aria-label="필수" className={styles.required}>*</span>
        </label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          aria-describedby={errors.password ? "login-password-error" : undefined}
          className={`${styles.input} ${errors.password ? styles.inputError : ""}`}
          {...register("password")}
        />
        {errors.password && (
          <p id="login-password-error" role="alert" className={styles.fieldError}>
            {errors.password.message}
          </p>
        )}
      </div>

      {oauthOnlyHint && (
        <div role="status" aria-live="polite" className={hintStyles.oauthOnlyHint}>
          <p className={hintStyles.oauthOnlyMessage}>{oauthOnlyHint.message}</p>
          <div className={hintStyles.providerButtonRow}>
            {oauthOnlyHint.providers.map((provider) => (
              <button
                key={provider}
                type="button"
                onClick={() => handleProviderLogin(provider)}
                aria-label={`${PROVIDER_LABEL[provider]}로 로그인`}
                className={`${popupStyles.socialBtn} ${PROVIDER_BTN_CLASS[provider]} ${hintStyles.emphasizedPulse}`}
              >
                <span className={popupStyles.socialIcon}>
                  {provider === "kakao" ? <KakaoIcon /> : provider === "naver" ? <NaverIcon /> : <GoogleIcon />}
                </span>
                <span className={popupStyles.socialLabel}>{PROVIDER_LABEL[provider]}로 로그인</span>
                <span className={popupStyles.socialSpacer} aria-hidden="true" />
              </button>
            ))}
          </div>
        </div>
      )}

      <label className={styles.persistRow}>
        <input
          type="checkbox"
          checked={preferPersist}
          onChange={(e) => setPreferPersist(e.target.checked)}
          className={styles.persistCheckbox}
        />
        <span className={styles.persistLabel}>로그인 상태 유지</span>
      </label>

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className={`${styles.primaryBtn} ${isSubmitting ? styles.primaryBtnLoading : ""}`}
      >
        {isSubmitting ? "로그인 중..." : "로그인"}
      </button>

      <div className={styles.linkRow}>
        <button
          type="button"
          onClick={onFindPassword ?? (() => {})}
          className={styles.linkBtn}
        >
          비밀번호 찾기
        </button>
        <button
          type="button"
          onClick={onFindId ?? (() => {})}
          className={styles.linkBtn}
        >
          아이디 찾기
        </button>
        <button
          type="button"
          onClick={onSignup ?? (() => {})}
          className={styles.linkBtnAccent}
        >
          회원가입
        </button>
      </div>
    </form>
  );
}

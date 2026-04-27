"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, type LoginFormValues } from "./schemas";
import { useSessionStore } from "@/stores/session-store";
import { login } from "./api";
import styles from "@/styles/auth-forms.module.css";

interface EmailLoginTabProps {
  onSignup?: () => void;
  onFindPassword?: () => void;
  onFindId?: () => void;
}

/** 이메일 로그인 탭 — 폼 UI + preferPersist 체크박스 + submit 처리. */
export function EmailLoginTab({ onSignup, onFindPassword, onFindId }: EmailLoginTabProps = {}) {
  const setPreferPersist = useSessionStore((s) => s.setPreferPersist);
  const preferPersist = useSessionStore((s) => s.preferPersist);
  const setUser = useSessionStore((s) => s.setUser);
  const closePopup = useSessionStore((s) => s.closePopup);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormValues) => {
    setServerError(null);
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
      const code = (err as { code?: string }).code;
      if (code === "AUTH_TEMPORARILY_LOCKED") {
        setServerError("잠시 후 다시 시도해주세요.");
      } else {
        setServerError("이메일 또는 비밀번호가 일치하지 않습니다.");
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

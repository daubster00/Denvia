"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, type LoginFormValues } from "./schemas";
import { useSessionStore } from "@/stores/session-store";
import { login } from "./api";

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
    <form onSubmit={handleSubmit(onSubmit)} noValidate style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {serverError && (
        <p role="alert" aria-live="assertive" style={{ color: "#EF4444", fontSize: 13, margin: 0, padding: "8px 12px", background: "#FEF2F2", borderRadius: 6 }}>
          {serverError}
        </p>
      )}
      <div>
        <label htmlFor="login-email" style={{ display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
          이메일 <span aria-label="필수" style={{ color: "#7C3AED" }}>*</span>
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "login-email-error" : undefined}
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
          <p id="login-email-error" role="alert" style={{ color: "#EF4444", fontSize: 12, marginTop: 4 }}>
            {errors.email.message}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="login-password" style={{ display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
          비밀번호 <span aria-label="필수" style={{ color: "#7C3AED" }}>*</span>
        </label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          aria-describedby={errors.password ? "login-password-error" : undefined}
          style={{
            width: "100%",
            padding: "10px 12px",
            border: `1px solid ${errors.password ? "#EF4444" : "#E1E2E4"}`,
            borderRadius: 8,
            fontSize: 14,
            outline: "none",
            boxSizing: "border-box",
          }}
          {...register("password")}
        />
        {errors.password && (
          <p id="login-password-error" role="alert" style={{ color: "#EF4444", fontSize: 12, marginTop: 4 }}>
            {errors.password.message}
          </p>
        )}
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", userSelect: "none" }}>
        <input
          type="checkbox"
          checked={preferPersist}
          onChange={(e) => setPreferPersist(e.target.checked)}
          style={{ width: 16, height: 16, accentColor: "#7C3AED" }}
        />
        <span style={{ fontSize: 14 }}>로그인 상태 유지</span>
      </label>

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
        {isSubmitting ? "로그인 중..." : "로그인"}
      </button>

      <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 4 }}>
        <button
          type="button"
          onClick={onFindPassword ?? (() => {})}
          style={{ background: "none", border: "none", color: "#70737C", fontSize: 13, cursor: "pointer", textDecoration: "underline" }}
        >
          비밀번호 찾기
        </button>
        <button
          type="button"
          onClick={onFindId ?? (() => {})}
          style={{ background: "none", border: "none", color: "#70737C", fontSize: 13, cursor: "pointer", textDecoration: "underline" }}
        >
          아이디 찾기
        </button>
        <button
          type="button"
          onClick={onSignup ?? (() => {})}
          style={{ background: "none", border: "none", color: "#7C3AED", fontSize: 13, cursor: "pointer", fontWeight: 600 }}
        >
          회원가입
        </button>
      </div>
    </form>
  );
}

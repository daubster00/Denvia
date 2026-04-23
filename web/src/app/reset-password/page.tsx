"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { resetPasswordSchema, type ResetPasswordFormValues } from "@/features/auth/schemas";
import { changePassword } from "@/features/auth/api";

/**
 * 임시 비밀번호 사용자의 비밀번호 재설정 페이지 (AC-5, AC-6).
 * must_reset_password=true인 세션에서만 진입 (SessionBootstrap 강제 라우팅).
 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
  });

  const onSubmit = async (data: ResetPasswordFormValues) => {
    setServerError(null);
    setIsSubmitting(true);
    try {
      await changePassword({ new_password: data.new_password });
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      router.push("/");
    } catch {
      setServerError("비밀번호 변경에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        padding: "40px 16px",
      }}
    >
      <div
        style={{
          width: "min(400px, calc(100vw - 32px))",
          backgroundColor: "#fff",
          borderRadius: 16,
          boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
          padding: "32px 28px",
        }}
      >
        <h1 style={{ margin: "0 0 8px", fontSize: 22, fontWeight: 700 }}>비밀번호 재설정</h1>
        <p style={{ margin: "0 0 24px", fontSize: 14, color: "#70737C" }}>
          임시 비밀번호로 로그인했습니다. 새 비밀번호를 설정해주세요.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} noValidate style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {serverError && (
            <p role="alert" aria-live="assertive" style={{ color: "#EF4444", fontSize: 13, margin: 0, padding: "8px 12px", background: "#FEF2F2", borderRadius: 6 }}>
              {serverError}
            </p>
          )}

          <div>
            <label htmlFor="new-password" style={{ display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
              새 비밀번호 <span aria-label="필수" style={{ color: "#7C3AED" }}>*</span>
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.new_password}
              aria-describedby={errors.new_password ? "new-pw-error" : undefined}
              style={{
                width: "100%",
                padding: "10px 12px",
                border: `1px solid ${errors.new_password ? "#EF4444" : "#E1E2E4"}`,
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                boxSizing: "border-box",
              }}
              {...register("new_password")}
            />
            {errors.new_password && (
              <p id="new-pw-error" role="alert" style={{ color: "#EF4444", fontSize: 12, marginTop: 4 }}>
                {errors.new_password.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="confirm-password" style={{ display: "block", marginBottom: 4, fontSize: 14, fontWeight: 500 }}>
              비밀번호 확인 <span aria-label="필수" style={{ color: "#7C3AED" }}>*</span>
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.confirm}
              aria-describedby={errors.confirm ? "confirm-pw-error" : undefined}
              style={{
                width: "100%",
                padding: "10px 12px",
                border: `1px solid ${errors.confirm ? "#EF4444" : "#E1E2E4"}`,
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                boxSizing: "border-box",
              }}
              {...register("confirm")}
            />
            {errors.confirm && (
              <p id="confirm-pw-error" role="alert" style={{ color: "#EF4444", fontSize: 12, marginTop: 4 }}>
                {errors.confirm.message}
              </p>
            )}
          </div>

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
            {isSubmitting ? "변경 중..." : "비밀번호 변경"}
          </button>
        </form>
      </div>
    </main>
  );
}

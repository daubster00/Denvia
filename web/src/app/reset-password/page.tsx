"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { resetPasswordSchema, type ResetPasswordFormValues } from "@/features/auth/schemas";
import { changePassword } from "@/features/auth/api";
import authStyles from "@/styles/auth-forms.module.css";
import pageStyles from "@/styles/reset-password.module.css";

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
    <main className={pageStyles.pageMain}>
      <div className={pageStyles.card}>
        <h1 className={pageStyles.pageTitle}>비밀번호 재설정</h1>
        <p className={pageStyles.pageDescription}>
          임시 비밀번호로 로그인했습니다. 새 비밀번호를 설정해주세요.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} noValidate className={authStyles.formColumn}>
          {serverError && (
            <p role="alert" aria-live="assertive" className={authStyles.serverErrorBanner}>
              {serverError}
            </p>
          )}

          <div>
            <label htmlFor="new-password" className={authStyles.fieldLabel}>
              새 비밀번호 <span aria-label="필수" className={authStyles.required}>*</span>
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.new_password}
              aria-describedby={errors.new_password ? "new-pw-error" : undefined}
              className={`${authStyles.input} ${errors.new_password ? authStyles.inputError : ""}`}
              {...register("new_password")}
            />
            {errors.new_password && (
              <p id="new-pw-error" role="alert" className={authStyles.fieldError}>
                {errors.new_password.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="confirm-password" className={authStyles.fieldLabel}>
              비밀번호 확인 <span aria-label="필수" className={authStyles.required}>*</span>
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.confirm}
              aria-describedby={errors.confirm ? "confirm-pw-error" : undefined}
              className={`${authStyles.input} ${errors.confirm ? authStyles.inputError : ""}`}
              {...register("confirm")}
            />
            {errors.confirm && (
              <p id="confirm-pw-error" role="alert" className={authStyles.fieldError}>
                {errors.confirm.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            aria-busy={isSubmitting}
            className={`${authStyles.primaryBtn} ${isSubmitting ? authStyles.primaryBtnLoading : ""}`}
          >
            {isSubmitting ? "변경 중..." : "비밀번호 변경"}
          </button>
        </form>
      </div>
    </main>
  );
}

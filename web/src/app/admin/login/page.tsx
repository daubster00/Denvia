"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { adminLogin, adminFetchMe } from "@/features/admin-auth/api";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { ApiError } from "@/types/api";
import styles from "./login.module.css";

interface AdminLoginFormValues {
  email: string;
  password: string;
}

export default function AdminLoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const setAdmin = useAdminSessionStore((s) => s.setAdmin);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AdminLoginFormValues>({ mode: "onSubmit" });

  // 이미 관리자 세션이 살아있다면 /admin으로
  useEffect(() => {
    let cancelled = false;
    void adminFetchMe()
      .then((admin) => {
        if (!cancelled) {
          setAdmin(admin);
          router.replace("/admin");
        }
      })
      .catch(() => {
        // 미인증은 정상 — 페이지 그대로 표시
      });
    return () => {
      cancelled = true;
    };
  }, [router, setAdmin]);

  const onSubmit = async (data: AdminLoginFormValues) => {
    setServerError(null);
    setIsSubmitting(true);
    try {
      const admin = await adminLogin({
        email: data.email,
        password: data.password,
      });
      // 로그인·로그아웃 모두 SPA 이동(새로고침 없음)이라 React Query 캐시가
      // 계정 전환 사이에 살아남는다. 새 계정으로 들어올 때 이전 계정의 캐시를
      // 반드시 비워, 등급이 다른 계정이 이전 응답을 그대로 보는 것을 차단한다.
      queryClient.clear();
      setAdmin(admin);
      router.replace("/admin");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === "ADMIN_PENDING_APPROVAL") {
          setServerError(
            "관리자 승인 대기 중입니다. 운영자 승인 후 이용 가능합니다.",
          );
        } else if (
          err.code === "AUTH_TEMPORARILY_LOCKED" ||
          err.code === "RATE_LIMITED"
        ) {
          setServerError("잠시 후 다시 시도해주세요.");
        } else {
          setServerError("이메일 또는 비밀번호가 일치하지 않습니다.");
        }
      } else {
        setServerError("이메일 또는 비밀번호가 일치하지 않습니다.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className={styles.shell}>
      <div className={styles.card}>
        <h1 className={styles.heading}>관리자 로그인</h1>
        <p className={styles.subheading}>
          이 페이지는 Denvia 운영자를 위한 별도 출입구입니다.
        </p>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className={styles.form}
        >
          {serverError && (
            <p role="alert" aria-live="assertive" className={styles.errorBanner}>
              {serverError}
            </p>
          )}

          <div className={styles.field}>
            <label htmlFor="admin-login-email" className={styles.label}>
              이메일
            </label>
            <input
              id="admin-login-email"
              type="email"
              autoComplete="email"
              aria-invalid={!!errors.email}
              className={`${styles.input} ${errors.email ? styles.inputError : ""}`}
              {...register("email", {
                required: "이메일을 입력해주세요.",
                pattern: {
                  value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                  message: "이메일 형식이 올바르지 않습니다.",
                },
              })}
            />
            {errors.email && (
              <p role="alert" className={styles.fieldError}>
                {errors.email.message}
              </p>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="admin-login-password" className={styles.label}>
              비밀번호
            </label>
            <input
              id="admin-login-password"
              type="password"
              autoComplete="current-password"
              aria-invalid={!!errors.password}
              className={`${styles.input} ${errors.password ? styles.inputError : ""}`}
              {...register("password", {
                required: "비밀번호를 입력해주세요.",
              })}
            />
            {errors.password && (
              <p role="alert" className={styles.fieldError}>
                {errors.password.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            aria-busy={isSubmitting}
            className={styles.submit}
          >
            {isSubmitting ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <p className={styles.footnote}>세션 1시간 후 자동 만료됩니다.</p>

        <div className={styles.signupRow}>
          <Link href="/admin/signup" className={styles.signupLink}>
            관리자 가입
          </Link>
        </div>
      </div>
    </main>
  );
}

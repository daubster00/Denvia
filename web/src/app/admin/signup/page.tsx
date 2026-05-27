"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { adminSignup } from "@/features/admin-auth/api";
import { ApiError } from "@/types/api";
import styles from "./signup.module.css";

interface AdminSignupFormValues {
  name: string;
  email: string;
  password: string;
}

const PHONE_FORMATTED = /^010-\d{4}-\d{4}$/;

function formatPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
}

export default function AdminSignupPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<AdminSignupFormValues>({ mode: "onChange" });

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPhone(formatPhone(e.target.value));
    setPhoneError(null);
  };

  const onSubmit = async (data: AdminSignupFormValues) => {
    if (!PHONE_FORMATTED.test(phone)) {
      setPhoneError("올바른 연락처를 입력하세요. (010-XXXX-XXXX)");
      return;
    }
    setServerError(null);
    setIsSubmitting(true);
    try {
      const digits = phone.replace(/\D/g, "");
      await adminSignup({
        name: data.name.trim(),
        email: data.email,
        password: data.password,
        phone: digits,
      });
      setSuccessMessage(
        "가입 신청이 접수되었습니다. 운영자 승인 후 로그인 가능합니다.",
      );
      setTimeout(() => router.replace("/admin/login"), 2000);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === "ACCOUNT_EMAIL_DUPLICATE") {
          setServerError("이미 사용 중인 이메일입니다.");
        } else if (err.code === "ACCOUNT_PHONE_DUPLICATE") {
          setServerError("이미 사용 중인 연락처입니다.");
        } else {
          setServerError(err.message || "가입 신청에 실패했습니다.");
        }
      } else {
        setServerError("가입 신청에 실패했습니다.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const phoneFilled = PHONE_FORMATTED.test(phone);
  const submitDisabled =
    !isValid || !phoneFilled || isSubmitting || successMessage !== null;

  return (
    <main className={styles.shell}>
      <div className={styles.card}>
        <h1 className={styles.heading}>관리자 가입 신청</h1>
        <p className={styles.subheading}>
          Denvia 운영자 권한을 신청하는 페이지입니다.
        </p>

        <div className={styles.infoCard} role="note">
          관리자 가입은 운영자 승인 후 이용 가능합니다.
          <br />
          승인까지 평균 1영업일 소요됩니다.
        </div>

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

          {successMessage && (
            <p role="status" aria-live="polite" className={styles.successBanner}>
              {successMessage}
            </p>
          )}

          <div className={styles.field}>
            <label htmlFor="admin-signup-name" className={styles.label}>
              이름<span className={styles.required}>*</span>
            </label>
            <input
              id="admin-signup-name"
              type="text"
              autoComplete="name"
              aria-invalid={!!errors.name}
              className={`${styles.input} ${errors.name ? styles.inputError : ""}`}
              {...register("name", {
                required: "이름을 입력해주세요.",
                maxLength: {
                  value: 50,
                  message: "이름은 50자 이하여야 합니다.",
                },
                validate: (v) =>
                  v.trim().length > 0 || "이름을 입력해주세요.",
              })}
            />
            {errors.name && (
              <p role="alert" className={styles.fieldError}>
                {errors.name.message}
              </p>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="admin-signup-email" className={styles.label}>
              이메일<span className={styles.required}>*</span>
            </label>
            <input
              id="admin-signup-email"
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
            <label htmlFor="admin-signup-phone" className={styles.label}>
              연락처<span className={styles.required}>*</span>
            </label>
            <input
              id="admin-signup-phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              placeholder="010-0000-0000"
              value={phone}
              onChange={handlePhoneChange}
              aria-invalid={!!phoneError}
              className={`${styles.input} ${phoneError ? styles.inputError : ""}`}
            />
            {phoneError && (
              <p role="alert" className={styles.fieldError}>
                {phoneError}
              </p>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="admin-signup-password" className={styles.label}>
              비밀번호<span className={styles.required}>*</span>
            </label>
            <input
              id="admin-signup-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.password}
              className={`${styles.input} ${errors.password ? styles.inputError : ""}`}
              {...register("password", {
                required: "비밀번호를 입력해주세요.",
                minLength: {
                  value: 8,
                  message: "비밀번호는 8자 이상이어야 합니다.",
                },
              })}
            />
            {errors.password ? (
              <p role="alert" className={styles.fieldError}>
                {errors.password.message}
              </p>
            ) : (
              <p className={styles.fieldHint}>8자 이상 입력해주세요.</p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitDisabled}
            aria-busy={isSubmitting}
            className={styles.submit}
          >
            {isSubmitting ? "신청 중..." : "가입 신청"}
          </button>
        </form>

        <div className={styles.disclaimer}>
          이 페이지는 Denvia 운영 관리자 가입 신청 전용입니다.
          <br />
          서비스 사용자는{" "}
          <Link href="/" className={styles.mainLink}>
            메인 페이지
          </Link>
          에서 가입해주세요.
        </div>

        <Link href="/admin/login" className={styles.backLink}>
          ← 로그인으로 돌아가기
        </Link>
      </div>
    </main>
  );
}

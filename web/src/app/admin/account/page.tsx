"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  changeAdminPassword,
  fetchAdminProfile,
  updateAdminProfile,
  type AdminProfile,
} from "@/features/admin-auth/api";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { ApiError } from "@/types/api";
import styles from "./page.module.css";

/**
 * 입력 숫자열을 자릿수에 맞게 010-XXXX-XXXX 모양으로 점진적으로 포맷한다.
 * - 0~3자  : "010"
 * - 4~7자  : "010-XXXX"
 * - 8자 이상: "010-XXXX-XXXX" (최대 11자리까지만 유지)
 */
function formatPhoneDisplay(raw: string): string {
  const digits = raw.replace(/[^0-9]/g, "").slice(0, 11);
  if (digits.length === 0) return "";
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
}

export default function AdminAccountPage() {
  const qc = useQueryClient();
  const setAdmin = useAdminSessionStore((s) => s.setAdmin);
  const sessionAdmin = useAdminSessionStore((s) => s.admin);

  const profileQuery = useQuery({
    queryKey: ["admin", "auth", "profile"],
    queryFn: fetchAdminProfile,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>관리자 계정</h1>
        <p className={styles.caption}>
          현재 로그인한 관리자의 정보를 수정합니다. 관리자 ID는 변경할 수 없습니다.
        </p>
      </header>

      {profileQuery.isLoading && (
        <p className={styles.statusMessage} role="status">
          계정 정보를 불러오는 중…
        </p>
      )}

      {!profileQuery.isLoading && profileQuery.error && (
        <section className={styles.errorBox} role="alert">
          <p>계정 정보를 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => profileQuery.refetch()}
          >
            다시 시도
          </button>
        </section>
      )}

      {profileQuery.data && (
        <>
          <AccountSummaryCard profile={profileQuery.data} />
          <ProfileEditCard
            profile={profileQuery.data}
            onUpdated={(updated) => {
              qc.setQueryData(["admin", "auth", "profile"], updated);
              // 탑네비/세션 store도 동기화 — 이메일·등급이 즉시 반영되도록.
              if (sessionAdmin) {
                setAdmin({
                  ...sessionAdmin,
                  email: updated.email,
                  is_master: updated.is_master,
                });
              }
              qc.invalidateQueries({ queryKey: ["admin-session"] });
            }}
          />
          <PasswordChangeCard />
        </>
      )}
    </section>
  );
}

function AccountSummaryCard({ profile }: { profile: AdminProfile }) {
  return (
    <section
      className={styles.card}
      aria-labelledby="admin-account-summary-title"
    >
      <h2 id="admin-account-summary-title" className={styles.cardTitle}>
        기본 정보
      </h2>
      <dl className={styles.summary}>
        <div className={styles.summaryRow}>
          <dt>관리자 ID</dt>
          <dd>#{profile.user_id}</dd>
        </div>
        <div className={styles.summaryRow}>
          <dt>등급</dt>
          <dd>
            <span
              className={
                profile.is_master ? styles.gradeMaster : styles.gradeAdmin
              }
            >
              {profile.grade_label}
            </span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

interface ProfileEditCardProps {
  profile: AdminProfile;
  onUpdated: (updated: AdminProfile) => void;
}

function ProfileEditCard({ profile, onUpdated }: ProfileEditCardProps) {
  const [email, setEmail] = useState(profile.email);
  const [phone, setPhone] = useState(
    profile.phone ? formatPhoneDisplay(profile.phone) : "",
  );
  const [name, setName] = useState(profile.name ?? "");
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setEmail(profile.email);
    setPhone(profile.phone ? formatPhoneDisplay(profile.phone) : "");
    setName(profile.name ?? "");
  }, [profile.email, profile.phone, profile.name]);

  const mutation = useMutation({
    mutationFn: updateAdminProfile,
    onSuccess: (updated) => {
      setSavedMessage("저장되었습니다.");
      setErrorMessage(null);
      onUpdated(updated);
      window.setTimeout(() => setSavedMessage(null), 2500);
    },
    onError: (err) => {
      setSavedMessage(null);
      if (err instanceof ApiError) {
        if (err.code === "ACCOUNT_EMAIL_DUPLICATE") {
          setErrorMessage("이미 사용 중인 이메일입니다.");
          return;
        }
        if (err.code === "ACCOUNT_PHONE_DUPLICATE") {
          setErrorMessage("이미 사용 중인 휴대폰 번호입니다.");
          return;
        }
        setErrorMessage(err.message);
        return;
      }
      setErrorMessage("저장에 실패했습니다.");
    },
  });

  const normalizedEmail = email.trim().toLowerCase();
  const normalizedPhone = phone.replace(/[^0-9]/g, "");
  const normalizedName = name.trim();

  const emailChanged = normalizedEmail !== profile.email;
  const phoneChanged = normalizedPhone !== (profile.phone ?? "");
  const nameChanged = normalizedName !== (profile.name ?? "");
  const isDirty = emailChanged || phoneChanged || nameChanged;

  const isEmailValid =
    normalizedEmail.includes("@") &&
    normalizedEmail.split("@")[1]?.includes(".");
  const isPhoneValid =
    normalizedPhone === "" || /^010\d{8}$/.test(normalizedPhone);
  const isValid = isEmailValid && isPhoneValid;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isDirty || !isValid || mutation.isPending) return;
    setErrorMessage(null);

    const payload: {
      email?: string;
      phone?: string | null;
      name?: string | null;
    } = {};
    if (emailChanged) payload.email = normalizedEmail;
    if (phoneChanged) payload.phone = normalizedPhone === "" ? null : normalizedPhone;
    if (nameChanged) payload.name = normalizedName === "" ? null : normalizedName;

    mutation.mutate(payload);
  };

  return (
    <section
      className={styles.card}
      aria-labelledby="admin-account-profile-title"
    >
      <h2 id="admin-account-profile-title" className={styles.cardTitle}>
        계정 정보 수정
      </h2>
      <p className={styles.cardCaption}>
        이메일은 다음 로그인부터 새 값으로 사용됩니다. 연락처는 010-XXXX-XXXX 형식의 휴대폰 번호만 허용합니다.
      </p>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="admin-account-email">
            이메일
          </label>
          <input
            id="admin-account-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={styles.input}
            autoComplete="email"
            required
          />
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="admin-account-phone">
            연락처
          </label>
          <input
            id="admin-account-phone"
            type="tel"
            inputMode="numeric"
            value={phone}
            onChange={(e) => setPhone(formatPhoneDisplay(e.target.value))}
            className={styles.input}
            placeholder="010-0000-0000"
            autoComplete="tel"
            maxLength={13}
          />
          <p className={styles.fieldHint}>
            비워두면 등록된 연락처가 삭제됩니다.
          </p>
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="admin-account-name">
            이름
          </label>
          <input
            id="admin-account-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={styles.input}
            maxLength={50}
            autoComplete="name"
          />
        </div>

        {errorMessage && (
          <p className={styles.errorText} role="alert">
            {errorMessage}
          </p>
        )}
        {savedMessage && (
          <p className={styles.successText} role="status">
            {savedMessage}
          </p>
        )}

        <div className={styles.actions}>
          <button
            type="submit"
            className={styles.saveBtn}
            disabled={!isDirty || !isValid || mutation.isPending}
          >
            {mutation.isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </form>
    </section>
  );
}

function PasswordChangeCard() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: changeAdminPassword,
    onSuccess: () => {
      setSavedMessage("비밀번호가 변경되었습니다.");
      setErrorMessage(null);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      window.setTimeout(() => setSavedMessage(null), 2500);
    },
    onError: (err) => {
      setSavedMessage(null);
      if (err instanceof ApiError) {
        if (err.code === "AUTH_INVALID_CREDENTIALS") {
          setErrorMessage("현재 비밀번호가 일치하지 않습니다.");
          return;
        }
        setErrorMessage(err.message);
        return;
      }
      setErrorMessage("비밀번호 변경에 실패했습니다.");
    },
  });

  const newPasswordValid = newPassword.length >= 8;
  const confirmMatches =
    confirmPassword.length > 0 && confirmPassword === newPassword;
  const canSubmit =
    currentPassword.length > 0 &&
    newPasswordValid &&
    confirmMatches &&
    !mutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setErrorMessage(null);
    mutation.mutate({
      current_password: currentPassword,
      new_password: newPassword,
    });
  };

  return (
    <section
      className={styles.card}
      aria-labelledby="admin-account-password-title"
    >
      <h2 id="admin-account-password-title" className={styles.cardTitle}>
        비밀번호 변경
      </h2>
      <p className={styles.cardCaption}>
        현재 비밀번호 확인 후 신규 비밀번호로 교체합니다. 8자 이상이어야 합니다.
      </p>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <div className={styles.field}>
          <label
            className={styles.fieldLabel}
            htmlFor="admin-account-current-password"
          >
            현재 비밀번호
          </label>
          <input
            id="admin-account-current-password"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className={styles.input}
            autoComplete="current-password"
            required
          />
        </div>

        <div className={styles.field}>
          <label
            className={styles.fieldLabel}
            htmlFor="admin-account-new-password"
          >
            새 비밀번호
          </label>
          <input
            id="admin-account-new-password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className={styles.input}
            autoComplete="new-password"
            minLength={8}
            required
          />
          <p className={styles.fieldHint}>8자 이상 입력하세요.</p>
        </div>

        <div className={styles.field}>
          <label
            className={styles.fieldLabel}
            htmlFor="admin-account-confirm-password"
          >
            새 비밀번호 확인
          </label>
          <input
            id="admin-account-confirm-password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className={styles.input}
            autoComplete="new-password"
            required
          />
          {confirmPassword.length > 0 && !confirmMatches && (
            <p className={styles.errorText}>
              새 비밀번호와 일치하지 않습니다.
            </p>
          )}
        </div>

        {errorMessage && (
          <p className={styles.errorText} role="alert">
            {errorMessage}
          </p>
        )}
        {savedMessage && (
          <p className={styles.successText} role="status">
            {savedMessage}
          </p>
        )}

        <div className={styles.actions}>
          <button
            type="submit"
            className={styles.saveBtn}
            disabled={!canSubmit}
          >
            {mutation.isPending ? "변경 중…" : "비밀번호 변경"}
          </button>
        </div>
      </form>
    </section>
  );
}

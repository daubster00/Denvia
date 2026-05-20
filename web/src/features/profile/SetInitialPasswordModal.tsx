"use client";

/**
 * 초기 비밀번호 설정 모달 — 소셜 가입자(password_hash IS NULL) 또는 임시 비밀번호
 * 발급 직후 사용자 전용. 기존 비밀번호 확인 단계는 없다.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/types/api";
import { useToastStore } from "@/stores/toast-store";
import authForm from "@/styles/auth-forms.module.css";
import styles from "./ProfileModal.module.css";
import { setInitialPassword } from "./api";

interface Props {
  open: boolean;
  onClose: () => void;
}

const ERROR_COPY: Record<string, string> = {
  PASSWORD_ALREADY_SET: "이미 비밀번호가 설정되어 있습니다. 비밀번호 변경 경로를 이용해주세요.",
  PASSWORD_TOO_SHORT: "비밀번호는 8자 이상이어야 합니다.",
};

export function SetInitialPasswordModal({ open, onClose }: Props) {
  const showToast = useToastStore((s) => s.show);
  const qc = useQueryClient();

  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setNewPw("");
      setConfirmPw("");
      setSubmitting(false);
      setErrMsg(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const handleSubmit = async () => {
    setErrMsg(null);
    if (newPw.length < 8) {
      setErrMsg("비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    if (newPw !== confirmPw) {
      setErrMsg("비밀번호와 확인이 일치하지 않습니다.");
      return;
    }
    setSubmitting(true);
    try {
      await setInitialPassword(newPw);
      showToast("비밀번호가 설정되었습니다.", 3000);
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["session"] });
      onClose();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      setErrMsg(ERROR_COPY[code] ?? "설정에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.dimmer} role="presentation">
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="pw-init-heading"
      >
        <h2 id="pw-init-heading" className={styles.heading}>
          비밀번호 설정
        </h2>
        <p className={styles.description}>
          이메일/비밀번호 로그인을 추가로 사용할 수 있게 비밀번호를 설정합니다.
          소셜 로그인은 그대로 사용 가능합니다.
        </p>

        <div>
          <label htmlFor="pw-init-new" className={authForm.fieldLabel}>
            새 비밀번호
          </label>
          <input
            id="pw-init-new"
            type="password"
            autoComplete="new-password"
            className={authForm.input}
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label htmlFor="pw-init-confirm" className={authForm.fieldLabel}>
            비밀번호 확인
          </label>
          <input
            id="pw-init-confirm"
            type="password"
            autoComplete="new-password"
            className={errMsg ? `${authForm.input} ${authForm.inputError}` : authForm.input}
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
          />
          {errMsg && (
            <p role="alert" className={authForm.fieldError}>
              {errMsg}
            </p>
          )}
        </div>

        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={submitting}
          >
            취소
          </button>
          <button
            type="button"
            className={styles.submitBtn}
            onClick={handleSubmit}
            disabled={submitting || newPw.length === 0 || confirmPw.length === 0}
          >
            {submitting ? "처리 중..." : "등록"}
          </button>
        </div>
      </div>
    </div>
  );
}

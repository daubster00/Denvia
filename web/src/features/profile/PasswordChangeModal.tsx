"use client";

/**
 * 비밀번호 변경 모달 — 이메일 가입자 전용 2단계 흐름.
 *
 * 1단계: 기존 비밀번호 입력 → 서버에서 검증(잘못된 PW면 401, 카운터 증가)
 * 2단계: 새 비밀번호 + 확인 입력 → /me/password/change 호출(서버가 한 번에 처리)
 *
 * 1단계는 클라이언트에서 별도 검증 호출을 하지 않는다(중복 API 호출 방지).
 * 사용자가 1단계 통과 후 2단계에서 입력한 새 PW와 함께 single round-trip으로 보낸다.
 * 잘못된 현재 PW는 서버에서 401 + 카운터 증가로 처리.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/types/api";
import { useToastStore } from "@/stores/toast-store";
import authForm from "@/styles/auth-forms.module.css";
import styles from "./ProfileModal.module.css";
import { changePasswordWithCurrent } from "./api";

interface Props {
  open: boolean;
  onClose: () => void;
}

type Step = "current" | "new";

const ERROR_COPY: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: "현재 비밀번호가 일치하지 않습니다.",
  AUTH_TEMPORARILY_LOCKED: "비밀번호 확인 실패가 누적되어 잠시 잠겼습니다. 잠시 후 다시 시도해주세요.",
  NO_PASSWORD_SET: "소셜 가입 계정은 초기 비밀번호 설정 경로를 사용해주세요.",
  PASSWORD_TOO_SHORT: "비밀번호는 8자 이상이어야 합니다.",
};

export function PasswordChangeModal({ open, onClose }: Props) {
  const showToast = useToastStore((s) => s.show);
  const qc = useQueryClient();

  const [step, setStep] = useState<Step>("current");
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setStep("current");
      setCurrentPw("");
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

  const handleNext = () => {
    if (currentPw.length === 0) {
      setErrMsg("기존 비밀번호를 입력해주세요.");
      return;
    }
    setErrMsg(null);
    setStep("new");
  };

  const handleSubmit = async () => {
    setErrMsg(null);
    if (newPw.length < 8) {
      setErrMsg("새 비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    if (newPw !== confirmPw) {
      setErrMsg("새 비밀번호와 확인이 일치하지 않습니다.");
      return;
    }
    setSubmitting(true);
    try {
      await changePasswordWithCurrent({
        current_password: currentPw,
        new_password: newPw,
      });
      showToast("비밀번호가 변경되었습니다.", 3000);
      qc.invalidateQueries({ queryKey: ["profile"] });
      onClose();
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      // 현재 PW 오류면 1단계로 되돌리기 — 사용자가 다시 입력할 수 있게.
      if (code === "AUTH_INVALID_CREDENTIALS") {
        setErrMsg(ERROR_COPY[code]);
        setStep("current");
        setCurrentPw("");
      } else {
        setErrMsg(ERROR_COPY[code] ?? "변경에 실패했습니다. 잠시 후 다시 시도해주세요.");
      }
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
        aria-labelledby="pw-change-heading"
      >
        <h2 id="pw-change-heading" className={styles.heading}>
          {step === "current" ? "기존 비밀번호 확인" : "새 비밀번호 등록"}
        </h2>
        <p className={styles.description}>
          {step === "current"
            ? "본인 확인을 위해 현재 사용 중인 비밀번호를 입력해주세요."
            : "새 비밀번호를 8자 이상으로 입력하고 한 번 더 확인해주세요."}
        </p>

        {step === "current" && (
          <div>
            <label htmlFor="pw-current" className={authForm.fieldLabel}>
              현재 비밀번호
            </label>
            <input
              id="pw-current"
              type="password"
              autoComplete="current-password"
              className={errMsg ? `${authForm.input} ${authForm.inputError}` : authForm.input}
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              autoFocus
            />
            {errMsg && (
              <p role="alert" className={authForm.fieldError}>
                {errMsg}
              </p>
            )}
          </div>
        )}

        {step === "new" && (
          <>
            <div>
              <label htmlFor="pw-new" className={authForm.fieldLabel}>
                새 비밀번호
              </label>
              <input
                id="pw-new"
                type="password"
                autoComplete="new-password"
                className={authForm.input}
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                autoFocus
              />
            </div>
            <div>
              <label htmlFor="pw-confirm" className={authForm.fieldLabel}>
                새 비밀번호 확인
              </label>
              <input
                id="pw-confirm"
                type="password"
                autoComplete="new-password"
                className={
                  errMsg ? `${authForm.input} ${authForm.inputError}` : authForm.input
                }
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
              />
              {errMsg && (
                <p role="alert" className={authForm.fieldError}>
                  {errMsg}
                </p>
              )}
            </div>
          </>
        )}

        <div className={styles.actionRow}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onClose}
            disabled={submitting}
          >
            취소
          </button>
          {step === "current" ? (
            <button
              type="button"
              className={styles.submitBtn}
              onClick={handleNext}
              disabled={currentPw.length === 0}
            >
              다음
            </button>
          ) : (
            <button
              type="button"
              className={styles.submitBtn}
              onClick={handleSubmit}
              disabled={submitting || newPw.length === 0 || confirmPw.length === 0}
            >
              {submitting ? "처리 중..." : "변경"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

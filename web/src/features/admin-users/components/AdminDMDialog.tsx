"use client";

import { useEffect, useRef, useState } from "react";
import {
  sendAdminDM,
  UserPermissionUpdateError,
} from "@/features/admin-users/api/users";
import styles from "./AdminDMDialog.module.css";

interface Props {
  open: boolean;
  targetUserId: number;
  targetEmail: string;
  onClose: () => void;
  onSent?: () => void;
}

const TITLE_MAX = 200;
const BODY_MAX = 5000;

export function AdminDMDialog({
  open,
  targetUserId,
  targetEmail,
  onClose,
  onSent,
}: Props) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setTitle("");
      setBody("");
      setError(null);
      // 다이얼로그 마운트 직후 제목 포커스
      const t = window.setTimeout(() => titleRef.current?.focus(), 0);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) {
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  const trimmedTitle = title.trim();
  const trimmedBody = body.trim();
  const canSubmit =
    !submitting &&
    trimmedTitle.length > 0 &&
    trimmedTitle.length <= TITLE_MAX &&
    trimmedBody.length > 0 &&
    trimmedBody.length <= BODY_MAX;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    if (
      !window.confirm(
        `${targetEmail} 사용자에게 쪽지를 전송합니다. 진행할까요?`,
      )
    ) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // 본문은 줄바꿈을 <br>로 보존하여 단순 텍스트 입력도 가독성을 유지한다.
      // 서버에서 nh3 sanitize가 한 번 더 적용된다.
      const bodyHtml = trimmedBody
        .split("\n")
        .map((line) => line || "&nbsp;")
        .join("<br>");
      await sendAdminDM(targetUserId, {
        title: trimmedTitle,
        body_html: bodyHtml,
      });
      onSent?.();
      onClose();
    } catch (err) {
      if (err instanceof UserPermissionUpdateError) {
        setError(err.message);
      } else {
        setError("쪽지 발송 중 오류가 발생했습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-dm-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <form className={styles.dialog} onSubmit={handleSubmit}>
        <h2 id="admin-dm-title" className={styles.title}>
          개별 쪽지 보내기
        </h2>

        <div className={styles.target}>
          받는 사람:&nbsp;
          <span className={styles.targetEmail}>{targetEmail}</span>
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="admin-dm-title-input">
            제목
          </label>
          <input
            id="admin-dm-title-input"
            ref={titleRef}
            className={styles.input}
            type="text"
            value={title}
            maxLength={TITLE_MAX}
            placeholder="안내 사항 제목"
            onChange={(e) => setTitle(e.target.value)}
            disabled={submitting}
          />
          <div className={styles.helperRow}>
            <span></span>
            <span>
              {trimmedTitle.length} / {TITLE_MAX}
            </span>
          </div>
        </div>

        <div className={styles.fieldGroup}>
          <label className={styles.label} htmlFor="admin-dm-body-input">
            내용
          </label>
          <textarea
            id="admin-dm-body-input"
            className={styles.textarea}
            value={body}
            maxLength={BODY_MAX}
            placeholder="사용자에게 전달할 내용을 입력해주세요."
            onChange={(e) => setBody(e.target.value)}
            disabled={submitting}
          />
          <div className={styles.helperRow}>
            <span>줄바꿈은 그대로 표시됩니다.</span>
            <span>
              {trimmedBody.length} / {BODY_MAX}
            </span>
          </div>
        </div>

        {error ? (
          <div className={styles.errorBox} role="alert">
            {error}
          </div>
        ) : null}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.cancel}
            onClick={onClose}
            disabled={submitting}
          >
            취소
          </button>
          <button
            type="submit"
            className={styles.submit}
            disabled={!canSubmit}
          >
            {submitting ? "발송 중…" : "보내기"}
          </button>
        </div>
      </form>
    </div>
  );
}

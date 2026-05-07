"use client";

/** 쪽지(공지) 작성 다이얼로그 — Story 7.1.
 *
 * 작성 즉시 발행 + target_segment의 모든 사용자 inbox로 fan-out된다.
 * 편집 미지원(스냅샷 보존) — 잘못 발행 시 삭제 후 재작성.
 */

import { useEffect, useRef, useState } from "react";

import {
  NoticeApiError,
  noticeFormSchema,
  type NoticeFormInput,
  type NoticeTargetSegment,
} from "../api/notice";
import styles from "./NoticeCreateDialog.module.css";

interface NoticeCreateDialogProps {
  isSubmitting: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSubmit: (input: NoticeFormInput) => void;
}

const SEGMENT_OPTIONS: Array<{ value: NoticeTargetSegment; label: string }> = [
  { value: "all", label: "전체" },
  { value: "doctor", label: "치과의사" },
  { value: "hygienist", label: "치과위생사" },
  { value: "student_other", label: "학생/기타" },
];

export function NoticeCreateDialog({
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: NoticeCreateDialogProps) {
  const [title, setTitle] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [targetSegment, setTargetSegment] =
    useState<NoticeTargetSegment>("all");
  const [fieldErrors, setFieldErrors] = useState<{
    title?: string;
    body_html?: string;
  }>({});
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    titleRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !isSubmitting) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, isSubmitting]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = noticeFormSchema.safeParse({
      title,
      body_html: bodyHtml,
      target_segment: targetSegment,
    });
    if (!parsed.success) {
      const next: { title?: string; body_html?: string } = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if (key === "title") next.title = issue.message;
        if (key === "body_html") next.body_html = issue.message;
      }
      setFieldErrors(next);
      return;
    }
    setFieldErrors({});
    onSubmit(parsed.data);
  }

  return (
    <>
      <div
        aria-hidden="true"
        className={styles.overlay}
        onClick={() => {
          if (!isSubmitting) onClose();
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="notice-create-title"
        className={styles.dialog}
      >
        <header className={styles.header}>
          <h2 id="notice-create-title" className={styles.title}>
            새 쪽지 작성
          </h2>
          <p className={styles.caption}>
            저장 즉시 대상 사용자의 쪽지함으로 발송됩니다. 잘못 발송한 쪽지는 목록에서 삭제하면 회수됩니다.
          </p>
        </header>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.field}>
            <span className={styles.label}>제목</span>
            <input
              ref={titleRef}
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              className={styles.input}
              disabled={isSubmitting}
              required
            />
            {fieldErrors.title && (
              <span className={styles.error}>{fieldErrors.title}</span>
            )}
          </label>

          <label className={styles.field}>
            <span className={styles.label}>본문</span>
            <textarea
              value={bodyHtml}
              onChange={(e) => setBodyHtml(e.target.value)}
              maxLength={20000}
              rows={8}
              className={styles.textarea}
              disabled={isSubmitting}
              required
            />
            <span className={styles.hint}>
              HTML 태그를 쓸 수 있지만, 안전한 태그만 통과합니다.
            </span>
            {fieldErrors.body_html && (
              <span className={styles.error}>{fieldErrors.body_html}</span>
            )}
          </label>

          <label className={styles.field}>
            <span className={styles.label}>대상</span>
            <select
              value={targetSegment}
              onChange={(e) =>
                setTargetSegment(e.target.value as NoticeTargetSegment)
              }
              className={styles.select}
              disabled={isSubmitting}
            >
              {SEGMENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          {errorMessage && (
            <p className={styles.errorBox} role="alert">
              {errorMessage}
            </p>
          )}

          <footer className={styles.footer}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={onClose}
              disabled={isSubmitting}
            >
              취소
            </button>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={isSubmitting}
            >
              {isSubmitting ? "발송 중…" : "발송"}
            </button>
          </footer>
        </form>
      </div>
    </>
  );
}

export { NoticeApiError };

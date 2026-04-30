"use client";

/** 고객문의 폼 모달 — Story 4.5 (F-504).
 *
 * 422 응답: 한글 message + details 인라인 표시.
 * 429 응답: 인라인 "잠시 후 다시 시도해주세요(분당 3회 제한)".
 * 성공: showToast + 모달 close.
 */

import { useEffect, useRef, useState } from "react";

import { useToastStore } from "@/stores/toast-store";
import { ApiError } from "@/types/api";

import { useSubmitInquiry } from "../hooks/useSubmitInquiry";
import styles from "./InquirySubmitDialog.module.css";

interface InquirySubmitDialogProps {
  onClose: () => void;
}

const SUBJECT_MAX = 200;
const BODY_MAX = 5000;

export function InquirySubmitDialog({ onClose }: InquirySubmitDialogProps) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const subjectRef = useRef<HTMLInputElement>(null);
  const showToast = useToastStore((s) => s.show);
  const submit = useSubmitInquiry();

  useEffect(() => {
    subjectRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function validate(): string | null {
    if (subject.trim().length === 0) return "제목을 입력해주세요.";
    if (subject.length > SUBJECT_MAX) {
      return `제목은 ${SUBJECT_MAX}자 이내로 입력해주세요.`;
    }
    if (body.trim().length === 0) return "문의 내용을 입력해주세요.";
    if (body.length > BODY_MAX) {
      return `문의 내용은 ${BODY_MAX}자 이내로 입력해주세요.`;
    }
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = validate();
    if (v) {
      setError(v);
      return;
    }
    setError(null);
    try {
      await submit.mutateAsync({ subject, body });
      showToast("문의가 접수되었습니다. 빠른 시일 내 답변드리겠습니다");
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "RATE_LIMITED") {
          setError("잠시 후 다시 시도해주세요(분당 3회 제한)");
        } else {
          setError(err.message || "잠시 문제가 생겼어요. 다시 시도해주세요");
        }
      } else {
        setError("잠시 문제가 생겼어요. 다시 시도해주세요");
      }
    }
  }

  return (
    <>
      <div aria-hidden="true" className={styles.overlay} onClick={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="inquiry-title"
        className={styles.dialog}
      >
        <div className={styles.header}>
          <h2 id="inquiry-title" className={styles.title}>
            고객 문의
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className={styles.closeBtn}
          >
            ✕
          </button>
        </div>
        <p className={styles.intro}>
          궁금한 점이나 불편한 사항을 알려주세요. 영업일 기준 1~2일 내 답변드립니다.
        </p>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label className={styles.field}>
            <span className={styles.label}>제목</span>
            <input
              ref={subjectRef}
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={SUBJECT_MAX}
              placeholder="예: 결제가 두 번 청구된 것 같아요"
              required
              className={styles.input}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>문의 내용</span>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={BODY_MAX}
              rows={8}
              placeholder="어떤 도움이 필요하신가요?"
              required
              className={styles.textarea}
            />
            <span className={styles.counter}>
              {body.length} / {BODY_MAX}
            </span>
          </label>
          {error && (
            <p role="alert" className={styles.error}>
              {error}
            </p>
          )}
          <div className={styles.actions}>
            <button
              type="button"
              onClick={onClose}
              className={styles.cancelBtn}
            >
              취소
            </button>
            <button
              type="submit"
              disabled={submit.isPending}
              className={styles.submitBtn}
            >
              {submit.isPending ? "제출 중…" : "제출"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

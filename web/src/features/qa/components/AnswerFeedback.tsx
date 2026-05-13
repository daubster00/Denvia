"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { IconDislike, IconLike } from "@wanteddev/wds-icon";
import { submitFeedback } from "@/features/qa/api/qa-feedback";
import styles from "./AnswerFeedback.module.css";

interface AnswerFeedbackProps {
  qaLogId: number;
}

export function AnswerFeedback({ qaLogId }: AnswerFeedbackProps) {
  const [rating, setRating] = useState<"good" | "bad" | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
  }, []);

  const mutation = useMutation({
    mutationFn: (r: "good" | "bad") => submitFeedback(qaLogId, r),
    onSuccess: (data) => {
      setRating(data.rating);
      setErrorText(null);
    },
    onError: (err) => {
      const code = (err as { code?: string }).code;
      const status = (err as { status?: number }).status;
      const text =
        code === "QA_LOG_NOT_FOUND" || status === 404
          ? "평가할 수 없는 답변입니다."
          : "평가 전송에 실패했습니다. 잠시 후 다시 시도해주세요.";
      setErrorText(text);
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      errorTimerRef.current = setTimeout(() => setErrorText(null), 3000);
    },
  });

  const isPending = mutation.isPending;

  const buttonClass = (active: boolean) =>
    [
      styles.btn,
      active ? styles.btnActive : "",
      isPending ? styles.btnDisabled : "",
    ]
      .filter(Boolean)
      .join(" ");

  return (
    <div className={styles.row} aria-label="답변 피드백">
      <button
        type="button"
        aria-label="도움이 됐어요"
        aria-pressed={rating === "good"}
        disabled={isPending}
        onClick={() => mutation.mutate("good")}
        className={buttonClass(rating === "good")}
      >
        <IconLike aria-hidden="true" className={styles.icon} />
      </button>
      <button
        type="button"
        aria-label="도움이 안 됐어요"
        aria-pressed={rating === "bad"}
        disabled={isPending}
        onClick={() => mutation.mutate("bad")}
        className={buttonClass(rating === "bad")}
      >
        <IconDislike aria-hidden="true" className={styles.icon} />
      </button>
      {errorText && (
        <span role="status" aria-live="polite" className={styles.errorText}>
          {errorText}
        </span>
      )}
    </div>
  );
}

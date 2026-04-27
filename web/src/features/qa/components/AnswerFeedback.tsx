"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { submitFeedback } from "@/features/qa/api/qa-feedback";

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

  const activeStyle: React.CSSProperties = {
    padding: "4px 10px",
    borderRadius: 8,
    border: "none",
    background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
    cursor: "pointer",
    fontSize: 13,
    color: "#FFFFFF",
  };

  const inactiveStyle: React.CSSProperties = {
    padding: "4px 10px",
    borderRadius: 8,
    border: "1px solid #E1E2E4",
    background: "none",
    cursor: "pointer",
    fontSize: 13,
    color: "#5A5C63",
  };

  const disabledStyle: React.CSSProperties = {
    cursor: "not-allowed",
    opacity: 0.6,
  };

  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}
      aria-label="답변 피드백"
    >
      <button
        type="button"
        aria-label="도움이 됐어요"
        aria-pressed={rating === "good"}
        disabled={isPending}
        onClick={() => mutation.mutate("good")}
        style={{
          ...(rating === "good" ? activeStyle : inactiveStyle),
          ...(isPending ? disabledStyle : {}),
        }}
      >
        👍
      </button>
      <button
        type="button"
        aria-label="도움이 안 됐어요"
        aria-pressed={rating === "bad"}
        disabled={isPending}
        onClick={() => mutation.mutate("bad")}
        style={{
          ...(rating === "bad" ? activeStyle : inactiveStyle),
          ...(isPending ? disabledStyle : {}),
        }}
      >
        👎
      </button>
      {errorText && (
        <span
          role="status"
          aria-live="polite"
          style={{ marginLeft: 4, fontSize: 12, color: "#DC2626" }}
        >
          {errorText}
        </span>
      )}
    </div>
  );
}

"use client";

interface AnswerFeedbackProps {
  qaLogId: number;
}

const _stub = () => console.warn("Story 2.4에서 구현");

export function AnswerFeedback({ qaLogId: _qaLogId }: AnswerFeedbackProps) {
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 8 }} aria-label="답변 피드백">
      <button
        type="button"
        aria-label="도움이 됐어요"
        onClick={_stub}
        style={{
          padding: "4px 10px",
          borderRadius: 8,
          border: "1px solid #E1E2E4",
          background: "none",
          cursor: "pointer",
          fontSize: 13,
          color: "#5A5C63",
        }}
      >
        👍
      </button>
      <button
        type="button"
        aria-label="도움이 안 됐어요"
        onClick={_stub}
        style={{
          padding: "4px 10px",
          borderRadius: 8,
          border: "1px solid #E1E2E4",
          background: "none",
          cursor: "pointer",
          fontSize: 13,
          color: "#5A5C63",
        }}
      >
        👎
      </button>
    </div>
  );
}

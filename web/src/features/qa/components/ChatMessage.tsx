"use client";

import type { QAMessage } from "@/stores/qa-store";
import { AdvisoryChip } from "./AdvisoryChip";
import { AnswerFeedback } from "./AnswerFeedback";

interface ChatMessageProps {
  message: QAMessage;
  onRetry?: () => void;
}

export function ChatMessage({ message, onRetry }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isPending = message.status === "pending";
  const isError = message.status === "error";

  if (isUser) {
    return (
      <div
        role="article"
        aria-live="polite"
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 12,
        }}
      >
        <div
          style={{
            maxWidth: "70%",
            padding: "12px 16px",
            backgroundColor: "#EDE9FE",
            borderRadius: "16px 16px 4px 16px",
            fontSize: 15,
            color: "#171719",
            lineHeight: 1.55,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div
      role="article"
      aria-live="polite"
      style={{
        display: "flex",
        justifyContent: "flex-start",
        marginBottom: 12,
      }}
    >
      <div
        style={{
          maxWidth: "80%",
          padding: "12px 16px",
          backgroundColor: "#FFFFFF",
          borderRadius: "16px 16px 16px 4px",
          borderLeft: "3px solid",
          borderImage: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%) 1",
          fontSize: 15,
          color: "#171719",
          lineHeight: 1.55,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
        }}
      >
        {isPending ? (
          <div
            role="status"
            aria-live="polite"
            style={{ display: "flex", alignItems: "center", gap: 8, color: "#70737C" }}
          >
            <img src="/Loading_Progress.gif" alt="" aria-hidden="true" style={{ width: 20, height: 20 }} />
            <span>답변 생성 중…</span>
          </div>
        ) : isError ? (
          <div>
            <p style={{ margin: "0 0 8px", color: "#DC2626" }}>{message.content}</p>
            {onRetry && (
              <button
                onClick={onRetry}
                style={{
                  padding: "6px 14px",
                  fontSize: 13,
                  borderRadius: 8,
                  border: "1px solid #8B5CF6",
                  background: "transparent",
                  color: "#8B5CF6",
                  cursor: "pointer",
                }}
              >
                재시도
              </button>
            )}
          </div>
        ) : (
          <>
            <p style={{ margin: "0 0 10px" }}>{message.content}</p>
            <AdvisoryChip />
            {message.qaLogId != null && <AnswerFeedback qaLogId={message.qaLogId} />}
          </>
        )}
      </div>
    </div>
  );
}

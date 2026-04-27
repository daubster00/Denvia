"use client";

import type { QAMessage } from "@/stores/qa-store";
import { AdvisoryChip } from "./AdvisoryChip";
import { AnswerFeedback } from "./AnswerFeedback";
import styles from "./ChatMessage.module.css";

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
      <div role="article" aria-live="polite" className={styles.userRow}>
        <div className={styles.userBubble}>{message.content}</div>
      </div>
    );
  }

  return (
    <div role="article" aria-live="polite" className={styles.assistantRow}>
      <div className={styles.assistantBubble}>
        {isPending ? (
          <div role="status" aria-live="polite" className={styles.pendingRow}>
            <img
              src="/Loading_Progress.gif"
              alt=""
              aria-hidden="true"
              className={styles.pendingIcon}
            />
            <span>답변 생성 중…</span>
          </div>
        ) : isError ? (
          <div>
            <p className={styles.errorText}>{message.content}</p>
            {onRetry && (
              <button onClick={onRetry} className={styles.retryBtn}>
                재시도
              </button>
            )}
          </div>
        ) : (
          <>
            <p className={styles.assistantText}>{message.content}</p>
            <AdvisoryChip />
            {message.qaLogId != null && <AnswerFeedback qaLogId={message.qaLogId} />}
          </>
        )}
      </div>
    </div>
  );
}

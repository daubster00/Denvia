"use client";

import type { QAMessage } from "@/stores/qa-store";
import { AdvisoryChip } from "./AdvisoryChip";
import { AnswerFeedback } from "./AnswerFeedback";
import { QuestionReFrame } from "./QuestionReFrame";
import styles from "./ChatMessage.module.css";

interface ChatMessageProps {
  message: QAMessage;
  onRetry?: () => void;
  onPickReframeOption?: (option: string) => void;
}

export function ChatMessage({ message, onRetry, onPickReframeOption }: ChatMessageProps) {
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
            {/* message.content는 reframe 유무와 무관하게 1회만 표시 — UI/DB SoT 단일화 (AC-5/AC-6) */}
            <p className={styles.assistantText}>{message.content}</p>
            <AdvisoryChip />
            {message.reframe != null && onPickReframeOption != null && (
              <QuestionReFrame
                options={message.reframe.options}
                onPickOption={onPickReframeOption}
              />
            )}
            {message.qaLogId != null && <AnswerFeedback qaLogId={message.qaLogId} />}
          </>
        )}
      </div>
    </div>
  );
}

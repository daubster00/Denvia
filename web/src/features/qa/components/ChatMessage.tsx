"use client";

import Image from "next/image";
import type { QAMessage } from "@/stores/qa-store";
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
  // 첫 글자가 들어오기 전까지만 스피너를 보여준다. 글자가 흘러나오기 시작하면
  // 타자기 애니메이션이 보이도록 content를 즉시 렌더한다.
  const showSpinner = isPending && message.content.length === 0;

  if (isUser) {
    return (
      <div role="article" aria-live="polite" className={styles.userRow}>
        <div className={styles.userBubble}>{message.content}</div>
      </div>
    );
  }

  return (
    <div
      role="article"
      aria-live="polite"
      className={`${styles.assistantRow} ${showSpinner ? styles.assistantRowLoading : ""}`}
    >
      {showSpinner ? (
        <img
          src="/Loading_Progress.gif"
          alt=""
          aria-hidden="true"
          className={styles.loadingThinking}
        />
      ) : (
        <div aria-hidden="true" className={styles.assistantAvatar}>
          <Image
            src="/logo_symbol.png"
            alt=""
            width={88}
            height={78}
            className={styles.assistantAvatarImg}
          />
        </div>
      )}
      <div className={styles.assistantBubble}>
        {showSpinner ? (
          <div role="status" aria-live="polite" className={styles.pendingRow}>
            <span>생각중이야…</span>
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
            {/* pending 동안에는 타자기 애니메이션만 보이고, 부가 요소(reframe/feedback)는 finalize 후에만 렌더 */}
            {!isPending && (
              <>
                {message.qaLogId != null && (
                  <div className={styles.assistantFooter}>
                    <AnswerFeedback qaLogId={message.qaLogId} />
                  </div>
                )}
                {message.reframe != null && onPickReframeOption != null && (
                  <QuestionReFrame
                    options={message.reframe.options}
                    onPickOption={onPickReframeOption}
                  />
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

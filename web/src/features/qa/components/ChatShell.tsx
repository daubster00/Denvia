"use client";

import { useEffect, useRef } from "react";
import { useQAStore } from "@/stores/qa-store";
import { ChatInput } from "@/features/qa/ChatInput";
import { ChatMessage } from "@/features/qa/components/ChatMessage";
import styles from "@/styles/chat-shell.module.css";

interface ChatShellProps {
  inputValue: string;
  onInputChange: (v: string) => void;
  onSubmit: (text: string) => void;
  isStreaming: boolean;
  onRetry?: () => void;
}

/**
 * Story 2.7 — 채팅 쉘.
 *
 * `useQAStore.messages.length`만 의존하여 hero ↔ inline variant 자동 전환.
 * - messages.length === 0: hero (수직 중앙 정렬, 메시지 영역 미렌더)
 * - messages.length >= 1: inline (메시지 영역 + 하단 입력창)
 *
 * 별도 UI 상태 머신·local state 도입 금지(이중 진실 회피, AC-1 구현 메모).
 * 애니메이션은 chat-shell.module.css의 keyframes로 처리 (Framer Motion 등 신규 의존 금지 — NFR-P5).
 */
export function ChatShell({
  inputValue,
  onInputChange,
  onSubmit,
  isStreaming,
  onRetry,
}: ChatShellProps) {
  const messages = useQAStore((s) => s.messages);
  const isHero = messages.length === 0;
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isHero) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isHero]);

  if (isHero) {
    return (
      <div className={styles.shellHero}>
        <div className={styles.inputCenter}>
          <ChatInput
            variant="hero"
            interactive
            value={inputValue}
            onChange={onInputChange}
            onSubmit={onSubmit}
            loading={isStreaming}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.shellInline}>
      <div
        role="log"
        aria-label="대화 내역"
        aria-live="polite"
        className={styles.messages}
      >
        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            onRetry={
              msg.role === "assistant" && msg.status === "error"
                ? onRetry
                : undefined
            }
          />
        ))}
        <div ref={bottomRef} />
      </div>
      <div className={styles.inputBottom}>
        <ChatInput
          variant="inline"
          value={inputValue}
          onChange={onInputChange}
          onSubmit={onSubmit}
          loading={isStreaming}
        />
      </div>
    </div>
  );
}

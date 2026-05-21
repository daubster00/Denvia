"use client";

import { useEffect, useRef } from "react";
import { useQAStore } from "@/stores/qa-store";
import { ChatInput } from "@/features/qa/ChatInput";
import { ChatMessage } from "@/features/qa/components/ChatMessage";
import styles from "@/styles/chat-shell.module.css";

import type { RefObject } from "react";

interface ChatShellProps {
  inputValue: string;
  onInputChange: (v: string) => void;
  onSubmit: (text: string) => void;
  isStreaming: boolean;
  onRetry?: () => void;
  onPickReframeOption?: (option: string) => void;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
  /** useQuota 훅에서 내려받은 데이터 (AC-8, AC-9) */
  quotaData?: {
    subscription_status: string;
    remaining: number;
    daily_limit: number;
    delay_seconds: number;
    /** 입력창 위 회색 안내문구 — 빈 문자열이면 미노출 (관리자가 콘텐츠 페이지에서 편집) */
    free_delay_notice_text: string;
  } | null;
}

/**
 * Story 2.7 — 채팅 쉘.
 *
 * `useQAStore.messages.length`만 의존하여 hero ↔ inline variant 자동 전환.
 * - messages.length === 0: hero (수직 중앙 정렬, 메시지 영역 미렌더)
 * - messages.length >= 1: inline (메시지 영역 + 하단 입력창)
 *
 * Story 2.3 추가:
 * - FreeDelayBanner: 첫 질의 후 1회 노출 (localStorage 영속)
 * - 남은 횟수 caption: inputBottom 아래
 * - 한도 차단(429): 본 컴포넌트는 인라인 박스 렌더 책임 없음. useQAStream 이
 *   useAlertStore.show() 로 글로벌 AppAlert 모달을 띄우고 clearMessages 로
 *   shellHero 로 자동 복귀시킨다.
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
  onPickReframeOption,
  inputRef,
  quotaData,
}: ChatShellProps) {
  const messages = useQAStore((s) => s.messages);
  const isHero = messages.length === 0;
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isHero) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isHero]);

  const isPro = quotaData?.subscription_status === "pro";
  const delayNoticeText = quotaData?.free_delay_notice_text?.trim() ?? "";
  const delayNotice = delayNoticeText ? (
    <p role="note" className={styles.delayNotice}>
      {delayNoticeText}
    </p>
  ) : null;

  const remainingCaption = quotaData ? (
    isPro ? (
      <span className={styles.remainingCaption}>Pro — 무제한</span>
    ) : (
      <span className={styles.remainingCaption}>
        오늘 남은 질문: {Math.min(quotaData.remaining, quotaData.daily_limit)}/{quotaData.daily_limit}
      </span>
    )
  ) : null;

  if (isHero) {
    return (
      <div className={styles.shellHero}>
        <div className={styles.inputCenter}>
          {delayNotice}
          <ChatInput
            variant="hero"
            interactive
            value={inputValue}
            onChange={onInputChange}
            onSubmit={onSubmit}
            loading={isStreaming}
          />
          {remainingCaption}
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
            onPickReframeOption={onPickReframeOption}
          />
        ))}
        <div ref={bottomRef} />
      </div>
      <div className={styles.inputBottom}>
        {delayNotice}
        <ChatInput
          variant="inline"
          value={inputValue}
          onChange={onInputChange}
          onSubmit={onSubmit}
          loading={isStreaming}
          inputRef={inputRef}
        />
        {remainingCaption}
      </div>
    </div>
  );
}

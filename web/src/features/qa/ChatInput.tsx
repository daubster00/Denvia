"use client";

import { useRef, useEffect } from "react";
import { useSessionStore } from "@/stores/session-store";
import styles from "./ChatInput.module.css";

interface ChatInputProps {
  variant?: "hero" | "inline";
  /**
   * Story 2.7: hero variant 활성 모드 스위치.
   * - false (default): 비로그인 readonly 모드 — 클릭/포커스 시 로그인 팝업 오픈 (F-001).
   * - true: 로그인 후 활성 모드 — inline과 동일한 textarea 입력 동작.
   * inline variant는 본 prop과 무관하게 항상 활성.
   */
  interactive?: boolean;
  value?: string;
  onChange?: (v: string) => void;
  onSubmit?: (v: string) => void;
  loading?: boolean;
}

/**
 * 채팅 입력 컴포넌트.
 * hero variant + interactive=false: readonly, 클릭 시 로그인 팝업 오픈 (UX Spec §2.5).
 * hero variant + interactive=true: 활성 textarea, 데스크톱·태블릿에서만 자동 포커스 (모바일 iOS 키보드 자동 호출 방지).
 * inline variant: 활성 textarea, 항상 자동 포커스, Enter 전송 / Shift+Enter 줄바꿈, maxLength=2000.
 */
export function ChatInput({
  variant = "hero",
  interactive = false,
  value,
  onChange,
  onSubmit,
  loading = false,
}: ChatInputProps) {
  const openPopup = useSessionStore((s) => s.openPopup);
  const isHero = variant === "hero";
  const isReadonlyHero = isHero && !interactive;
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isReadonlyHero) return;
    const el = inputRef.current;
    if (!el) return;
    // 모바일에서는 자동 포커스 금지 — iOS 키보드 자동 호출 방지 (UX Spec §2.5).
    const isMobile =
      typeof window !== "undefined" &&
      window.matchMedia?.("(max-width: 767px)").matches;
    if (!isMobile) {
      el.focus();
    }
  }, [isReadonlyHero, isHero]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = (value ?? "").trim();
      if (text && !loading) {
        onSubmit?.(text);
      }
    }
  }

  if (isReadonlyHero) {
    return (
      <div className={styles.wrapper}>
        <input
          type="text"
          readOnly
          placeholder="무엇이든 물어보세요"
          aria-label="질문 입력 — 로그인 후 이용 가능"
          onClick={() => openPopup("email")}
          onFocus={() => openPopup("email")}
          className={`${styles.input} ${styles.inputReadonly}`}
        />
        <span aria-hidden="true" className={styles.iconHint}>
          ↑
        </span>
      </div>
    );
  }

  const trimmed = (value ?? "").trim();
  const sendDisabled = loading || !trimmed;

  return (
    <div className={styles.wrapper}>
      <textarea
        ref={inputRef}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="무엇이든 물어보세요"
        aria-label="질문 입력"
        maxLength={2000}
        rows={1}
        disabled={loading}
        className={styles.input}
      />
      <button
        type="button"
        aria-label="질문 전송"
        disabled={sendDisabled}
        onClick={() => {
          if (trimmed && !loading) onSubmit?.(trimmed);
        }}
        className={
          sendDisabled
            ? `${styles.sendBtn} ${styles.sendBtnDisabled}`
            : styles.sendBtn
        }
      >
        ↑
      </button>
    </div>
  );
}

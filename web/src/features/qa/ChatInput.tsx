"use client";

import { useRef, useEffect } from "react";
import { useSessionStore } from "@/stores/session-store";

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
      <div style={{ position: "relative", width: "100%", maxWidth: 640 }}>
        <input
          type="text"
          readOnly
          placeholder="무엇이든 물어보세요"
          aria-label="질문 입력 — 로그인 후 이용 가능"
          onClick={() => openPopup("email")}
          onFocus={() => openPopup("email")}
          style={{
            width: "100%",
            padding: "16px 52px 16px 20px",
            fontSize: 16,
            border: "1.5px solid #E1E2E4",
            borderRadius: 12,
            outline: "none",
            cursor: "pointer",
            backgroundColor: "#F7F7F8",
            color: "#5A5C63",
            boxSizing: "border-box",
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
            transition: "border-color 0.15s, box-shadow 0.15s",
          }}
        />
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            right: 16,
            top: "50%",
            transform: "translateY(-50%)",
            color: "#AEB0B6",
            fontSize: 20,
            pointerEvents: "none",
          }}
        >
          ↑
        </span>
      </div>
    );
  }

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 640 }}>
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
        style={{
          width: "100%",
          padding: "16px 52px 16px 20px",
          fontSize: 16,
          border: "1.5px solid #E1E2E4",
          borderRadius: 12,
          outline: "none",
          cursor: loading ? "not-allowed" : "text",
          backgroundColor: "#fff",
          boxSizing: "border-box",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
          transition: "border-color 0.15s, box-shadow 0.15s",
          resize: "none",
          overflow: "hidden",
          fontFamily: "inherit",
        }}
      />
      <button
        type="button"
        aria-label="질문 전송"
        disabled={loading || !(value ?? "").trim()}
        onClick={() => {
          const text = (value ?? "").trim();
          if (text && !loading) onSubmit?.(text);
        }}
        style={{
          position: "absolute",
          right: 12,
          top: "50%",
          transform: "translateY(-50%)",
          background: "none",
          border: "none",
          cursor: "pointer",
          color: loading || !(value ?? "").trim() ? "#AEB0B6" : "#7C3AED",
          fontSize: 20,
          padding: 4,
          display: "flex",
          alignItems: "center",
        }}
      >
        ↑
      </button>
    </div>
  );
}

"use client";

import { useSessionStore } from "@/stores/session-store";

interface ChatInputProps {
  variant?: "hero";
}

/**
 * 채팅 입력 컴포넌트.
 * hero variant: 비활성화 상태, 클릭/포커스 시 로그인 팝업 오픈 (F-001 트리거, UX Spec §2.5).
 */
export function ChatInput({ variant = "hero" }: ChatInputProps) {
  const openPopup = useSessionStore((s) => s.openPopup);
  const isHero = variant === "hero";

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        maxWidth: 640,
      }}
    >
      <input
        type="text"
        readOnly={isHero}
        placeholder="무엇이든 물어보세요"
        aria-label="질문 입력 — 로그인 후 이용 가능"
        onClick={isHero ? () => openPopup("email") : undefined}
        onFocus={isHero ? () => openPopup("email") : undefined}
        style={{
          width: "100%",
          padding: "16px 52px 16px 20px",
          fontSize: 16,
          border: "1.5px solid #E1E2E4",
          borderRadius: 12,
          outline: "none",
          cursor: isHero ? "pointer" : "text",
          backgroundColor: isHero ? "#F7F7F8" : "#fff",
          color: isHero ? "#5A5C63" : "inherit",
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
          color: isHero ? "#AEB0B6" : "#7C3AED",
          fontSize: 20,
          pointerEvents: "none",
        }}
      >
        ↑
      </span>
    </div>
  );
}

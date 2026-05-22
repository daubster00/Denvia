"use client";

import { useRef, useEffect, type RefObject } from "react";
import { useSessionStore } from "@/stores/session-store";
import { useAlertStore } from "@/stores/alert-store";
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
  /** Story 2.6: 외부 ref 주입 — chip 클릭 후 포커스 이동. 부재 시 내부 useRef 사용. */
  inputRef?: RefObject<HTMLTextAreaElement | null>;
  /**
   * 관리자가 이상탐지 UI 에서 question_only scope 으로 차단한 경우의 만료 시각 (ISO 8601).
   * null/undefined = 차단 없음. 미래 시각이면 입력창을 readonly 로 잠그고 클릭 시 모달로 안내.
   */
  blockedUntil?: string | null;
  blockReason?: string | null;
}

function formatBlockExpiry(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

/**
 * 채팅 입력 컴포넌트.
 * hero variant + interactive=false: readonly, 클릭 시 로그인 팝업 오픈 (UX Spec §2.5).
 * hero variant + interactive=true: 활성 textarea, 데스크톱·태블릿에서만 자동 포커스 (모바일 iOS 키보드 자동 호출 방지).
 * inline variant: 활성 textarea, 항상 자동 포커스, Enter 전송 / Shift+Enter 줄바꿈, maxLength=2000.
 * blockedUntil 가 미래 시각이면 위 모든 모드 위에 덮어 readonly + 클릭 시 차단 안내 모달 노출.
 */
export function ChatInput({
  variant = "hero",
  interactive = false,
  value,
  onChange,
  onSubmit,
  loading = false,
  inputRef: externalRef,
  blockedUntil,
  blockReason,
}: ChatInputProps) {
  const openPopup = useSessionStore((s) => s.openPopup);
  const showAlert = useAlertStore((s) => s.show);
  const isHero = variant === "hero";
  const isReadonlyHero = isHero && !interactive;
  const isBlocked =
    !!blockedUntil && new Date(blockedUntil).getTime() > Date.now();
  const internalRef = useRef<HTMLTextAreaElement>(null);
  // 외부 ref 우선, 부재 시 내부 ref — 기존 자동 포커스 effect 보존 (Story 2.6)
  const inputRef = externalRef ?? internalRef;

  useEffect(() => {
    if (isReadonlyHero || isBlocked) return;
    const el = inputRef.current;
    if (!el) return;
    // 모바일에서는 자동 포커스 금지 — iOS 키보드 자동 호출 방지 (UX Spec §2.5).
    const isMobile =
      typeof window !== "undefined" &&
      window.matchMedia?.("(max-width: 767px)").matches;
    if (!isMobile) {
      el.focus();
    }
  }, [isReadonlyHero, isHero, isBlocked]);

  function openBlockedAlert() {
    const expiry = blockedUntil ? formatBlockExpiry(blockedUntil) : "";
    const reasonLine =
      blockReason && blockReason.trim()
        ? `사유: ${blockReason.trim()}`
        : "사유: 관리자에 의해 일시적으로 질문이 제한되었습니다.";
    const expiryLine = expiry ? `해제 예정\n${expiry}` : "";
    showAlert({
      level: "warning",
      title: "이상 활동이 감지되어 질문이 일시 제한되었습니다.",
      description: [reasonLine, expiryLine].filter(Boolean).join("\n"),
      dedupeKey: "question_blocked",
    });
  }

  if (isBlocked) {
    // 차단 상태여도 UI 는 평소와 완전히 동일하게 보여야 한다. 사용자가
    // 클릭해야 비로소 차단을 알게 된다. 클릭 시 onMouseDown preventDefault 로
    // 입력 포커스를 막아 — 알림 닫은 뒤 포커스 복귀로 알림이 다시 뜨는 루프를 차단.
    return (
      <div className={styles.wrapper}>
        <textarea
          readOnly
          value=""
          placeholder="무엇이든 물어보세요"
          aria-label="질문 입력 — 일시 제한"
          rows={1}
          onMouseDown={(e) => {
            e.preventDefault();
            openBlockedAlert();
          }}
          onKeyDown={(e) => {
            e.preventDefault();
            openBlockedAlert();
          }}
          className={styles.input}
        />
        <button
          type="button"
          aria-label="질문 전송"
          disabled
          className={`${styles.sendBtn} ${styles.sendBtnDisabled}`}
          onMouseDown={(e) => {
            e.preventDefault();
            openBlockedAlert();
          }}
        >
          ↑
        </button>
      </div>
    );
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

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = (value ?? "").trim();
      if (text && !loading) {
        onSubmit?.(text);
      }
    }
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

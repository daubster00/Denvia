"use client";

import { useState, useRef, useCallback, type RefObject } from "react";
import { usePathname, useRouter } from "next/navigation";
import { TopNav } from "@/components/layout/TopNav";
import { AdvisoryChip } from "@/components/brand/AdvisoryChip";
import { ChatInput } from "@/features/qa/ChatInput";
import { ChatShell } from "@/features/qa/components/ChatShell";
import { useActivePopup } from "@/features/inbox/hooks/useActivePopup";
import { PopupModal } from "@/features/inbox/components/PopupModal";
import { useQAStore } from "@/stores/qa-store";
import { useQAStream } from "@/features/qa/hooks/useQAStream";
import { useQuota } from "@/features/qa/hooks/useQuota";
import { postClientEvent } from "@/features/qa/api/events";
import styles from "./QAHomeExperience.module.css";

export function AuthenticatedQAExperience() {
  const router = useRouter();
  const pathname = usePathname();
  const [inputValue, setInputValue] = useState("");
  const [showDelayBanner, setShowDelayBanner] = useState(false);
  const messages = useQAStore((s) => s.messages);
  const clearMessages = useQAStore((s) => s.clearMessages);
  const stream = useQAStream();
  const lastUserTextRef = useRef<string>("");
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const { data: quotaData } = useQuota();
  // Story 4.5 — 메인 페이지 진입 시 자동 노출 팝업 (FR31 / F-503).
  // /(메인) 진입에만 마운트(/chat 등 다른 라우트에서는 미적용).
  const { data: activePopup } = useActivePopup();

  const handleReset = useCallback(() => {
    stream.abort();
    clearMessages();
    void postClientEvent("qa.conversation.reset");
  }, [stream, clearMessages]);

  // Story 2.6: 새 질문 예시 클릭 → 입력창에 텍스트 삽입 + 포커스 이동 (자동 submit 미수행)
  const handlePickReframeOption = useCallback((option: string) => {
    setInputValue(option);
    // setState 후 다음 paint frame에서 포커스 — 텍스트 갱신 후 안정적 포커스 보장
    requestAnimationFrame(() => {
      chatInputRef.current?.focus();
    });
  }, []);

  async function handleSubmit(text: string) {
    lastUserTextRef.current = text;
    setInputValue("");
    setShowDelayBanner(true);
    if (pathname === "/") {
      router.push("/chat");
    }
    await stream.submit(text);
  }

  const isStreaming = messages.some(
    (m) => m.role === "assistant" && m.status === "pending"
  );
  // /(메인)는 항상 hero(HeroCopy + 활성 입력) — 제출 시 /chat 으로 이동.
  // /chat 은 항상 ChatShell — ChatShell 자체가 messages.length 로
  // shellHero(중앙 입력 + 남은 횟수 caption) ↔ shellInline 분기를 책임진다.
  // 한도 차단(429): useQAStream 이 useAlertStore.show() 로 글로벌 AppAlert 모달을
  // 띄우고 clearMessages 로 shellHero 로 자동 복귀시킨다.
  const isHero = pathname === "/";

  return (
    <>
      <TopNav onResetChat={handleReset} />
      {isHero ? (
        <HeroSection>
          <HeroCopy />
          <ChatInput
            variant="hero"
            interactive
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSubmit}
            loading={isStreaming}
          />
          <AdvisoryChip />
        </HeroSection>
      ) : (
        <ChatShell
          inputValue={inputValue}
          onInputChange={setInputValue}
          onSubmit={handleSubmit}
          isStreaming={isStreaming}
          onRetry={() => stream.submit(lastUserTextRef.current)}
          onPickReframeOption={handlePickReframeOption}
          inputRef={chatInputRef as RefObject<HTMLTextAreaElement | null>}
          quotaData={quotaData}
          showDelayBanner={showDelayBanner}
        />
      )}
      {/* Story 4.5 — 메인(/)에서만 자동 팝업 노출 */}
      {isHero && activePopup ? <PopupModal popup={activePopup} /> : null}
    </>
  );
}

export function HeroSection({ children }: { children: React.ReactNode }) {
  return (
    <section aria-label="서비스 소개" className={styles.heroSection}>
      <div className={styles.heroInner}>{children}</div>
    </section>
  );
}

export function HeroCopy() {
  return (
    <div className={styles.heroCopy}>
      <h1 className={styles.heroTitle}>
        치과 임상 질문,{" "}
        <span className={styles.heroTitleAccent}>AI가 참고 답변을 드립니다</span>
      </h1>
      <p className={styles.heroSubtitle}>
        치과 전문가를 위한 임상 Q&A 서비스. 최신 문헌을 기반으로 빠르고 신뢰할 수 있는 참고 답변을 제공합니다.
      </p>
    </div>
  );
}

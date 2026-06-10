"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { ChatInput } from "@/features/qa/ChatInput";
import { ChatShell } from "@/features/qa/components/ChatShell";
import { useQAStore } from "@/stores/qa-store";
import { useQAStream } from "@/features/qa/hooks/useQAStream";
import { useQuota } from "@/features/qa/hooks/useQuota";
import { postClientEvent } from "@/features/qa/api/events";
import { PopupCarousel } from "@/features/inbox/components/PopupCarousel";
import styles from "./QAHomeExperience.module.css";

export function AuthenticatedQAExperience() {
  const router = useRouter();
  const pathname = usePathname();
  const [inputValue, setInputValue] = useState("");
  const messages = useQAStore((s) => s.messages);
  const clearMessages = useQAStore((s) => s.clearMessages);
  // 홈(/)에서 보낸 질문은 /chat 으로 이동이 끝난 다음 스트림을 시작한다.
  // router.push + stream.submit 을 동시에 시작하면 라우팅 도중 도착한 첫 토큰이
  // 화면에 반영되지 않는 race 가 있었다(10:23 사용자 사례).
  // 페이지 라우팅(/ → /chat)으로 페이지 컴포넌트가 unmount/remount 되므로 useRef
  // 는 소실된다. zustand store(sessionStorage 영속)에 보관해야 살아남는다.
  const pendingHomeQuestion = useQAStore((s) => s.pendingHomeQuestion);
  const setPendingHomeQuestion = useQAStore((s) => s.setPendingHomeQuestion);
  const stream = useQAStream();
  const lastUserTextRef = useRef<string>("");
  const { data: quotaData } = useQuota();

  const handleReset = useCallback(() => {
    stream.abort();
    clearMessages();
    setPendingHomeQuestion(null);
    void postClientEvent("qa.conversation.reset");
  }, [stream, clearMessages, setPendingHomeQuestion]);

  async function handleSubmit(text: string) {
    lastUserTextRef.current = text;
    setInputValue("");
    if (pathname === "/") {
      setPendingHomeQuestion(text);
      router.push("/chat");
      return;
    }
    await stream.submit(text);
  }

  useEffect(() => {
    if (pathname !== "/chat") return;
    if (!pendingHomeQuestion) return;
    const text = pendingHomeQuestion;
    setPendingHomeQuestion(null);
    void stream.submit(text);
  }, [pathname, pendingHomeQuestion, setPendingHomeQuestion, stream]);

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
      {/* 팝업은 메인 랜딩(/)에서만 노출. /chat 등 다른 페이지에는 띄우지 않는다. */}
      {isHero && <PopupCarousel />}
      {isHero ? (
        <>
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
          </HeroSection>
          <Footer />
        </>
      ) : (
        <ChatShell
          inputValue={inputValue}
          onInputChange={setInputValue}
          onSubmit={handleSubmit}
          isStreaming={isStreaming}
          onRetry={() => stream.submit(lastUserTextRef.current)}
          quotaData={quotaData}
        />
      )}
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
      <DentalMark />
      <h1 className={styles.heroTitle}>
        치과 보험청구{" "}
        <span className={styles.heroTitleAccent}>Denvia AI에게 질문하세요.</span>
      </h1>
      <p className={styles.heroSubtitle}>
        데스크 행정업무 및 치과 보험청구에 관한 정보를 제공하는 치과전용 AI입니다.
      </p>
    </div>
  );
}

function DentalMark() {
  return (
    <Image
      src="/logo_symbol.png"
      alt="Denvia AI"
      className={styles.dentalMark}
      width={200}
      height={178}
      priority
    />
  );
}

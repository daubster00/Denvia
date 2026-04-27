"use client";

import { useState, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { TopNav } from "@/components/layout/TopNav";
import { AdvisoryChip } from "@/components/brand/AdvisoryChip";
import { ChatInput } from "@/features/qa/ChatInput";
import { ChatShell } from "@/features/qa/components/ChatShell";
import { CustomerInquiryFAB } from "@/components/feedback/CustomerInquiryFAB";
import { useSessionStore } from "@/stores/session-store";
import { fetchMe } from "@/features/auth/api";
import { useQAStore } from "@/stores/qa-store";
import { useQAStream } from "@/features/qa/hooks/useQAStream";
import { useQuota } from "@/features/qa/hooks/useQuota";
import { postClientEvent } from "@/features/qa/api/events";

/**
 * F-000 메인 랜딩 + Q&A 단일 페이지.
 *
 * 비로그인: 히어로 카피 + readonly ChatInput → 클릭 시 로그인 팝업 (F-001).
 * 로그인 + messages.length === 0: 히어로 카피 + 활성 ChatInput — 그 자리에서 바로 입력 가능.
 * 로그인 + messages.length >= 1: ChatShell inline (히어로 카피 숨김, 메시지 영역 + 하단 입력창).
 *
 * /chat 으로 redirect 하지 않는다 — 같은 페이지에서 hero ↔ inline 전환만 일어난다.
 * 로고 클릭 시 onResetChat 으로 messages clear → 다시 hero 로 복귀.
 *
 * 인증은 두 출처를 모두 인정한다:
 *   - useSessionStore.user: 팝업 로그인(EmailLoginTab → setUser)이 query invalidate 없이 채운 값
 *   - useQuery(["session"]).data: 직접 / 진입 시 SessionBootstrap이 띄운 동일 query 캐시
 */
export default function Home() {
  const user = useSessionStore((s) => s.user);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const isAuthenticated = !!user || (!!data && !isError);

  if (isAuthenticated) {
    return <AuthenticatedHome />;
  }
  return <UnauthenticatedHome isLoading={isLoading} />;
}

function UnauthenticatedHome({ isLoading }: { isLoading: boolean }) {
  return (
    <>
      <TopNav />
      <HeroSection>
        <HeroCopy />
        {isLoading ? (
          <div aria-hidden="true" style={{ width: "100%", maxWidth: 640, height: 56 }} />
        ) : (
          <ChatInput variant="hero" />
        )}
        <AdvisoryChip />
      </HeroSection>
    </>
  );
}

function AuthenticatedHome() {
  const [inputValue, setInputValue] = useState("");
  const [showDelayBanner, setShowDelayBanner] = useState(false);
  const messages = useQAStore((s) => s.messages);
  const clearMessages = useQAStore((s) => s.clearMessages);
  const stream = useQAStream();
  const lastUserTextRef = useRef<string>("");
  const { data: quotaData } = useQuota();

  const handleReset = useCallback(() => {
    stream.abort();
    clearMessages();
    void postClientEvent("qa.conversation.reset");
  }, [stream, clearMessages]);

  async function handleSubmit(text: string) {
    lastUserTextRef.current = text;
    setInputValue("");
    setShowDelayBanner(true);
    await stream.submit(text);
  }

  const isStreaming = messages.some(
    (m) => m.role === "assistant" && m.status === "pending"
  );
  const isHero = messages.length === 0;

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
          quotaData={quotaData}
          showDelayBanner={showDelayBanner}
        />
      )}
      <CustomerInquiryFAB />
    </>
  );
}

function HeroSection({ children }: { children: React.ReactNode }) {
  return (
    <>
      <section
        aria-label="서비스 소개"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "calc(100vh - 64px)",
          padding: "40px 16px 80px",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 720,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 32,
            textAlign: "center",
          }}
        >
          {children}
        </div>
      </section>
      <style>{`
        @media (max-width: 767px) {
          section[aria-label="서비스 소개"] {
            min-height: calc(100vh - 56px) !important;
          }
        }
        @media (min-width: 1280px) {
          section[aria-label="서비스 소개"] > div {
            max-width: 720px !important;
          }
        }
      `}</style>
    </>
  );
}

function HeroCopy() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
      <h1
        style={{
          margin: 0,
          fontSize: "clamp(26px, 4vw, 40px)",
          fontWeight: 700,
          color: "#171719",
          lineHeight: 1.25,
          letterSpacing: "-0.5px",
          textAlign: "center",
        }}
      >
        치과 임상 질문,{" "}
        <span
          style={{
            background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          AI가 참고 답변을 드립니다
        </span>
      </h1>
      <p
        style={{
          margin: "0 auto",
          fontSize: 16,
          color: "#70737C",
          lineHeight: 1.6,
          maxWidth: 480,
          textAlign: "center",
        }}
      >
        치과 전문가를 위한 임상 Q&A 서비스. 최신 문헌을 기반으로 빠르고 신뢰할 수 있는 참고 답변을 제공합니다.
      </p>
    </div>
  );
}

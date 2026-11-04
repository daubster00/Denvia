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
import { resolveRetryTarget } from "@/features/qa/lib/retry-target";
import { postClientEvent } from "@/features/qa/api/events";
import { PopupCarousel } from "@/features/inbox/components/PopupCarousel";
import { QANoticeModal } from "@/features/qa/components/QANoticeModal";
import {
  dismissQaNoticeForToday,
  isQaNoticeDismissedForToday,
} from "@/features/qa/lib/qa-notice-dismissal";
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

  // #130 ① — 질문 전송 안내 팝업. 매 질문마다 노출되며 답변 스트리밍을 막지 않는다.
  const [noticeOpen, setNoticeOpen] = useState(false);

  // 관리자가 팝업을 켜뒀고, 띄울 문구가 있고, "오늘 하루 보지 않기"로 차단되지
  // 않았을 때만 노출한다. 문구 확인은 #149 결정 ②(문구 삭제) 이후의 방어선 —
  // 서버도 빈 문구면 enabled 를 내려주지만, 빈 팝업이 뜨는 일은 양쪽에서 막는다.
  const maybeShowNotice = useCallback(() => {
    if (!quotaData?.qa_notice_enabled) return;
    if (!quotaData?.qa_notice_text?.trim()) return;
    if (isQaNoticeDismissedForToday()) return;
    setNoticeOpen(true);
  }, [quotaData?.qa_notice_enabled, quotaData?.qa_notice_text]);

  const handleReset = useCallback(() => {
    stream.abort();
    clearMessages();
    setPendingHomeQuestion(null);
    void postClientEvent("qa.conversation.reset");
  }, [stream, clearMessages, setPendingHomeQuestion]);

  /**
   * 오류 답변의 "다시 시도" (검수 P1-6 + 재수정 P1-2).
   *
   * 예전에는 어떤 답변의 버튼을 눌러도 **가장 최근 질문**을 다시 보냈다. 대화가 쌓이는
   * 지금은 위쪽 오류 답변을 눌렀을 때 엉뚱한 질문이 다시 전송된다.
   * 그 답변 바로 앞의 사용자 질문을 찾아 그 질문을 다시 보낸다.
   *
   * 맥락(이전 대화)도 **최초 요청 당시의 스냅샷**을 그대로 쓴다. 지금 화면 전체를
   * 다시 계산하면, A 가 실패한 뒤 정상 완료된 B 의 로그 id 까지 A 의 맥락으로
   * 들어간다 — 시간상 A 보다 뒤에 일어난 대화가 A 의 앞 맥락이 되는 셈이고,
   * 검색 질의가 엉뚱하게 완성되거나 저장 답변 재생 게이팅이 어긋난다.
   */
  const handleRetry = useCallback(
    (assistantMessageId: string) => {
      const target = resolveRetryTarget(
        useQAStore.getState().messages,
        assistantMessageId,
      );
      if (!target) return;
      lastUserTextRef.current = target.question;
      // retry:true — 전송 못 한 저장 답변이 있으면 같은 맥락일 때만 재생된다(P0-1).
      void stream.submit(target.question, {
        retry: true,
        historyTurnIds: target.historyTurnIds,
      });
    },
    [stream],
  );

  async function handleSubmit(text: string) {
    lastUserTextRef.current = text;
    setInputValue("");
    if (pathname === "/") {
      // 홈에서 보낸 질문은 /chat 도착 후 아래 effect 가 팝업을 띄운다.
      setPendingHomeQuestion(text);
      router.push("/chat");
      return;
    }
    // 팝업을 먼저 띄우고(전송과 동시), 뒤에서 스트림은 계속 진행한다.
    maybeShowNotice();
    await stream.submit(text);
  }

  useEffect(() => {
    if (pathname !== "/chat") return;
    if (!pendingHomeQuestion) return;
    const text = pendingHomeQuestion;
    setPendingHomeQuestion(null);
    maybeShowNotice();
    void stream.submit(text);
  }, [pathname, pendingHomeQuestion, setPendingHomeQuestion, stream, maybeShowNotice]);

  // "답변 중" 판정은 **마지막 메시지 하나만** 본다 (#149).
  // 대화가 쌓이게 되면서 some() 으로 전체를 훑으면, 과거에 중단된 답변 하나 때문에
  // 입력창이 영원히 잠긴다. 지금 진행 중인 턴은 언제나 맨 마지막이다.
  const lastMessage = messages[messages.length - 1];
  const isStreaming =
    lastMessage?.role === "assistant" && lastMessage.status === "pending";
  // /(메인)는 항상 hero(HeroCopy + 활성 입력) — 제출 시 /chat 으로 이동.
  // /chat 은 항상 ChatShell — ChatShell 자체가 messages.length 로
  // shellHero(중앙 입력 + 남은 횟수 caption) ↔ shellInline 분기를 책임진다.
  // 한도 차단(429): useQAStream 이 useAlertStore.show() 로 글로벌 AppAlert 모달을
  // 띄우고, 거절된 이번 턴만 dropTurn 으로 걷어낸다(과거 정상 대화는 보존 — 검수 P1-5).
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
          onRetry={handleRetry}
          quotaData={quotaData}
        />
      )}
      {/* #130 ① — 질문 전송 안내 팝업. /chat 에서만, 관리자 설정 값으로 렌더. */}
      {!isHero && quotaData ? (
        <QANoticeModal
          open={noticeOpen}
          text={quotaData.qa_notice_text}
          fontSize={quotaData.qa_notice_font_size}
          color={quotaData.qa_notice_color}
          fontWeight={quotaData.qa_notice_font_weight}
          width={quotaData.qa_notice_width}
          onConfirm={() => setNoticeOpen(false)}
          onDismissToday={() => {
            dismissQaNoticeForToday();
            setNoticeOpen(false);
          }}
        />
      ) : null}
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
    // unoptimized 이유는 LogoLink.tsx 주석 참고 (2026-09-17 로고 미표시 사고)
    <Image
      src="/logo_symbol.png"
      alt="Denvia AI"
      className={styles.dentalMark}
      width={200}
      height={178}
      priority
      unoptimized
    />
  );
}

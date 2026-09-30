"use client";

import { useEffect, useState, type ReactNode } from "react";
import Image from "next/image";
import type { QAMessage } from "@/stores/qa-store";
import { AnswerFeedback } from "./AnswerFeedback";
import styles from "./ChatMessage.module.css";

interface ChatMessageProps {
  message: QAMessage;
  onRetry?: () => void;
}

// 답변 본문에 포함된 URL을 자동으로 새 창에서 열리는 하이퍼링크로 변환한다.
// http(s):// 또는 www. 로 시작하는 URL을 인식하고, 뒤에 붙은 문장부호(., ), ] 등)는 링크에서 제외한다.
const URL_PATTERN = /(https?:\/\/[^\s<>"')\]]+|www\.[^\s<>"')\]]+)/gi;
const TRAILING_PUNCTUATION = /[.,!?;:)\]}"'»」』]+$/;

// 기다리는 동안 말을 거는 단계. 백엔드 첫 토큰 상한이 45초라 그 안에서 세 번 바뀐다.
//
// 왜 여러 번인가 — 문구가 한 번 뜨고 그대로 멈춰 있으면 화면이 굳은 것처럼 보인다.
// 2026-09-30 장애 때 실제로 한 사람이 같은 질문을 3번 다시 던졌다(14:33·14:34·14:35).
// 문구가 바뀌는 것 자체가 "아직 돌아가고 있다"는 신호다.
//
// 컴포넌트 밖에 두는 이유: 안에 두면 렌더마다 새 배열이 돼 타이머 effect 의 의존성이
// 매번 바뀐다(= 문구가 영영 안 바뀐다).
const SLOW_HINT_STAGES = [
  { afterMs: 7000, text: "복잡한 질문은 시간이 더 걸립니다." },
  { afterMs: 15000, text: "자료를 찾아보고 있어요. 조금만 기다려 주세요." },
  { afterMs: 30000, text: "평소보다 오래 걸리고 있어요. 곧 답변이 시작됩니다." },
] as const;

function renderWithLinks(text: string): ReactNode {
  if (!text) return text;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const start = match.index ?? 0;
    let url = match[0];
    const trail = url.match(TRAILING_PUNCTUATION);
    const trailing = trail ? trail[0] : "";
    if (trailing) url = url.slice(0, url.length - trailing.length);
    if (start > cursor) nodes.push(text.slice(cursor, start));
    const href = url.startsWith("www.") ? `https://${url}` : url;
    nodes.push(
      <a
        key={`lnk-${key++}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={styles.assistantLink}
      >
        {url}
      </a>
    );
    if (trailing) nodes.push(trailing);
    cursor = start + match[0].length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes.length > 0 ? nodes : text;
}

export function ChatMessage({ message, onRetry }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isPending = message.status === "pending";
  const isError = message.status === "error";
  // 첫 글자가 들어오기 전까지만 스피너를 보여준다. 글자가 흘러나오기 시작하면
  // 타자기 애니메이션이 보이도록 content를 즉시 렌더한다.
  const showSpinner = isPending && message.content.length === 0;

  // -1 = 아직 아무 문구도 띄우지 않음
  const [hintStage, setHintStage] = useState(-1);
  useEffect(() => {
    if (!showSpinner) {
      setHintStage(-1);
      return;
    }
    const timers = SLOW_HINT_STAGES.map((stage, i) =>
      setTimeout(() => setHintStage(i), stage.afterMs)
    );
    return () => timers.forEach(clearTimeout);
  }, [showSpinner]);

  if (isUser) {
    return (
      <div role="article" aria-live="polite" className={styles.userRow}>
        <div className={styles.userBubble}>{message.content}</div>
      </div>
    );
  }

  return (
    <div
      role="article"
      aria-live="polite"
      className={`${styles.assistantRow} ${showSpinner ? styles.assistantRowLoading : ""}`}
    >
      {showSpinner ? (
        <img
          src="/Loading_Progress.gif"
          alt=""
          aria-hidden="true"
          className={styles.loadingThinking}
        />
      ) : (
        <div aria-hidden="true" className={styles.assistantAvatar}>
          <Image
            src="/logo_symbol.png"
            alt=""
            width={88}
            height={78}
            className={styles.assistantAvatarImg}
          />
        </div>
      )}
      <div className={styles.assistantBubble}>
        {showSpinner ? (
          <div role="status" aria-live="polite" className={styles.pendingRow}>
            <span>생각중이야…</span>
            {hintStage >= 0 && (
              <div className={styles.pendingSlowHint}>
                {SLOW_HINT_STAGES[hintStage].text}
              </div>
            )}
          </div>
        ) : isError ? (
          <div>
            {/* 끊기기 전까지 받은 부분 답변은 그대로 보여준다 (게시판 #141). */}
            {message.content && (
              <p className={styles.assistantText}>
                {renderWithLinks(message.content)}
              </p>
            )}
            <p className={styles.errorNotice}>
              {message.errorMessage ?? "답변이 중단됐어요. 다시 시도해 주세요."}
            </p>
            {onRetry && (
              <button onClick={onRetry} className={styles.retryBtn}>
                다시 시도
              </button>
            )}
          </div>
        ) : (
          <>
            <p className={styles.assistantText}>{renderWithLinks(message.content)}</p>
            {!isPending && message.qaLogId != null && (
              <div className={styles.assistantFooter}>
                <AnswerFeedback qaLogId={message.qaLogId} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

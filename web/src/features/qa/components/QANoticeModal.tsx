"use client";

import { useEffect, useRef, type CSSProperties } from "react";
import styles from "./QANoticeModal.module.css";

interface QANoticeModalProps {
  open: boolean;
  /** 관리자 편집 문구 */
  text: string;
  /** 본문 글자 크기(px) */
  fontSize: number;
  /** 본문 글자 색상(hex) */
  color: string;
  /** 본문 글자 두께(100~900) */
  fontWeight: number;
  /** 팝업 상자 가로폭(px) */
  width: number;
  /** "확인" — 팝업만 닫는다. */
  onConfirm: () => void;
  /** "오늘 하루 보지 않기" — 오늘(KST) 동안 재노출 차단 후 닫는다. */
  onDismissToday: () => void;
}

/**
 * #130 ① — 질문 전송 시 화면 정중앙에 뜨는 안내 팝업.
 *
 * 매 질문마다 노출되며 답변 스트리밍을 막지 않는다(질문 전송과 동시에 뜨고
 * 뒤에서 답변은 계속 진행). "확인"으로 닫거나 "오늘 하루 보지 않기"로
 * 오늘(KST) 동안 재노출을 막을 수 있다.
 *
 * 문구/글자크기/색상/두께/가로폭은 관리자가 설정한 런타임 값이므로 CSS 변수로
 * 주입한다(정적 스타일은 전부 module.css). ConfirmDialog 의 overlay+중앙정렬 패턴을 따른다.
 */
export function QANoticeModal({
  open,
  text,
  fontSize,
  color,
  fontWeight,
  width,
  onConfirm,
  onDismissToday,
}: QANoticeModalProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      // ESC 는 일반 닫기(확인과 동일) — 오늘 차단은 명시 버튼으로만.
      if (e.key === "Escape") onConfirm();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onConfirm]);

  if (!open) return null;

  // 관리자 런타임 값 → CSS 변수. module.css 가 이 변수들을 소비한다.
  const dialogStyle = {
    "--qa-notice-width": `${width}px`,
  } as CSSProperties;
  const textStyle = {
    "--qa-notice-font-size": `${fontSize}px`,
    "--qa-notice-color": color,
    "--qa-notice-font-weight": String(fontWeight),
  } as CSSProperties;

  return (
    <div
      role="presentation"
      className={styles.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onConfirm();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-describedby="qa-notice-text"
        className={styles.dialog}
        style={dialogStyle}
      >
        <p id="qa-notice-text" className={styles.text} style={textStyle}>
          {text}
        </p>

        <div className={styles.actions}>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={styles.confirmBtn}
          >
            확인
          </button>
          <button
            type="button"
            onClick={onDismissToday}
            className={styles.dismissBtn}
          >
            오늘 하루 보지 않기
          </button>
        </div>
      </div>
    </div>
  );
}

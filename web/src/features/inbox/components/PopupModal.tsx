"use client";

/** PopupModal — 메인 진입 시 자동 노출 팝업. Story 4.5 AC-9.
 *
 * X/ESC 클릭 시 POST /seen 호출 → 모달 close → invalidate.
 * 낙관적 UX(seen 응답 대기 X) — 실패 시 다음 진입 시 재노출.
 */

import { useEffect, useRef } from "react";

import { sanitizeNoticeHtml } from "@/lib/sanitize";
import type { ActivePopup } from "../types";
import { usePopupSeen } from "../hooks/usePopupSeen";
import styles from "./PopupModal.module.css";

interface PopupModalProps {
  popup: ActivePopup;
}

// 서버가 이미 http/https만 통과시키지만, 어드민 흐름·캐시 오염 등을 대비해 한 번 더 거른다.
function safeExternalHref(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://")) {
    return trimmed;
  }
  return null;
}

export function PopupModal({ popup }: PopupModalProps) {
  const seenMutation = usePopupSeen();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const safeLinkUrl = safeExternalHref(popup.link_url);

  function handleClose() {
    seenMutation.mutate(popup.popup_id);
  }

  useEffect(() => {
    closeBtnRef.current?.focus();
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") handleClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div aria-hidden="true" className={styles.overlay} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="popup-title"
        className={styles.dialog}
      >
        <div className={styles.header}>
          <h2 id="popup-title" className={styles.title}>
            {popup.title}
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={handleClose}
            aria-label="닫기"
            className={styles.closeBtn}
          >
            ✕
          </button>
        </div>
        <div
          className={styles.body}
          dangerouslySetInnerHTML={{
            __html: sanitizeNoticeHtml(popup.body_html_safe),
          }}
        />
        {safeLinkUrl && (
          <div className={styles.footer}>
            <a
              href={safeLinkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.linkBtn}
            >
              자세히 보기 ↗
            </a>
          </div>
        )}
      </div>
    </>
  );
}

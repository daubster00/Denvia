"use client";

/** NoticeDetailDialog — 쪽지함 카드 클릭 시 전체 본문 모달. Story 4.5. */

import { useEffect, useRef } from "react";

import { sanitizeNoticeHtml } from "@/lib/sanitize";
import type { InboxItem } from "../types";
import styles from "./NoticeDetailDialog.module.css";

interface NoticeDetailDialogProps {
  item: InboxItem;
  onClose: () => void;
}

export function NoticeDetailDialog({ item, onClose }: NoticeDetailDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeBtnRef.current?.focus();
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <>
      <div aria-hidden="true" className={styles.overlay} onClick={onClose} />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="notice-detail-title"
        className={styles.dialog}
      >
        <div className={styles.header}>
          <h2 id="notice-detail-title" className={styles.title}>
            {item.title}
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className={styles.closeBtn}
          >
            ✕
          </button>
        </div>
        <div
          className={styles.body}
          dangerouslySetInnerHTML={{
            __html: sanitizeNoticeHtml(item.body_html_safe),
          }}
        />
      </div>
    </>
  );
}

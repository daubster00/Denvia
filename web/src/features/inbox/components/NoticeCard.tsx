"use client";

/** NoticeCard — 쪽지함 카드 (UX-DR16). Story 4.5.
 *
 * radius-xl 16px + shadow-sm + 카카오톡 알림톡 스타일.
 * type 분기 아이콘·strip 색상 + 미읽음 좌측 strip + sanitize HTML 렌더.
 */

import type { InboxItem } from "../types";
import styles from "./NoticeCard.module.css";

interface NoticeCardProps {
  item: InboxItem;
  onClick: (messageId: number) => void;
}

const TYPE_LABEL: Record<InboxItem["type"], string> = {
  notice: "공지",
  system: "시스템",
  billing: "결제",
};

export function NoticeCard({ item, onClick }: NoticeCardProps) {
  const stripClass =
    item.type === "billing"
      ? styles.stripBilling
      : item.type === "system"
        ? styles.stripSystem
        : styles.stripNotice;

  const iconClass =
    item.type === "billing"
      ? styles.iconBilling
      : item.type === "system"
        ? styles.iconSystem
        : styles.iconNotice;

  return (
    <button
      type="button"
      role="article"
      aria-label={`${TYPE_LABEL[item.type]} 쪽지 — ${item.title}`}
      className={`${styles.card} ${item.is_read ? "" : styles.unread}`}
      onClick={() => onClick(item.message_id)}
    >
      <span className={`${styles.strip} ${stripClass}`} aria-hidden="true" />
      <span className={`${styles.icon} ${iconClass}`} aria-hidden="true">
        {iconForType(item.type)}
      </span>
      <span className={styles.body}>
        <span className={styles.titleRow}>
          <span className={styles.title}>{item.title}</span>
          {!item.is_read && <span className={styles.dot} aria-hidden="true" />}
        </span>
        <span className={styles.preview}>
          {stripHtml(item.body_html_safe)}
        </span>
        <span className={styles.timestamp}>{formatRelative(item.created_at)}</span>
      </span>
    </button>
  );
}

function iconForType(type: InboxItem["type"]): React.ReactNode {
  if (type === "billing") {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <line x1="2" y1="10" x2="22" y2="10" />
      </svg>
    );
  }
  if (type === "system") {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    );
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11l18-8v18l-18-8v-2z" />
    </svg>
  );
}

/** body_html에서 태그를 제거해 미리보기 2~3줄용 plain text 추출. */
function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
}

function formatRelative(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHr = Math.floor(diffMs / 3_600_000);
  const diffDay = Math.floor(diffMs / 86_400_000);
  if (diffMin < 1) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;
  if (diffHr < 24) return `${diffHr}시간 전`;
  if (diffDay < 2) return "어제";
  return date.toISOString().slice(0, 10);
}

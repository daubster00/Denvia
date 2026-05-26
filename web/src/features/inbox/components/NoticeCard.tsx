"use client";

/** NoticeCard — 쪽지함 카드 (UX-DR16). Story 4.5.
 *
 * radius-xl 16px + shadow-sm + 카카오톡 알림톡 스타일.
 * type 분기 아이콘·strip 색상 + 미읽음 좌측 strip + sanitize HTML 렌더.
 */

import { IconMail, IconCircleInfo, IconCoins, IconPerson } from "@wanteddev/wds-icon";

import type { InboxItem } from "../types";
import styles from "./NoticeCard.module.css";

interface NoticeCardProps {
  item: InboxItem;
  onClick: (messageId: number) => void;
  onDelete?: (messageId: number) => void;
}

const TYPE_LABEL: Record<InboxItem["type"], string> = {
  notice: "공지",
  system: "시스템",
  billing: "결제",
  admin_dm: "안내",
};

const TYPE_ICON = {
  notice: IconMail,
  system: IconCircleInfo,
  billing: IconCoins,
  admin_dm: IconPerson,
} as const;

const STRIP_CLASS: Record<InboxItem["type"], string> = {
  notice: styles.stripNotice,
  system: styles.stripSystem,
  billing: styles.stripBilling,
  admin_dm: styles.stripAdminDm,
};

const ICON_CLASS: Record<InboxItem["type"], string> = {
  notice: styles.iconNotice,
  system: styles.iconSystem,
  billing: styles.iconBilling,
  admin_dm: styles.iconAdminDm,
};

export function NoticeCard({ item, onClick, onDelete }: NoticeCardProps) {
  const TypeIcon = TYPE_ICON[item.type];

  return (
    <div
      className={`${styles.card} ${item.is_read ? "" : styles.unread}`}
    >
      <span className={`${styles.strip} ${STRIP_CLASS[item.type]}`} aria-hidden="true" />
      <button
        type="button"
        role="article"
        aria-label={`${TYPE_LABEL[item.type]} 쪽지 — ${item.title}`}
        className={styles.cardMain}
        onClick={() => onClick(item.message_id)}
      >
        <span className={`${styles.icon} ${ICON_CLASS[item.type]}`} aria-hidden="true">
          <TypeIcon />
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
      {onDelete ? (
        <button
          type="button"
          className={styles.deleteBtn}
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm("이 쪽지를 삭제하시겠습니까?\n삭제된 쪽지는 30일 후 완전히 사라집니다.")) {
              onDelete(item.message_id);
            }
          }}
          aria-label="쪽지 삭제"
          title="쪽지 삭제"
        >
          삭제
        </button>
      ) : null}
    </div>
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

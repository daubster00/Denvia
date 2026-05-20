"use client";

/** 쪽지함 미리보기 드롭다운 — Story 7.1.
 *
 * 동작:
 * - 로그인 후 마운트 시 자동으로 펼침. 같은 세션에서 X로 닫으면 다시 자동으로 뜨지 않음
 *   (sessionStorage `inbox_preview_dismissed` 플래그). 새 탭/세션에서는 재노출.
 * - 카드 클릭 → /inbox 로 이동(해당 메시지로 스크롤은 ?focus=<id>).
 * - 미읽음 0건이면 렌더 안 함(아이콘만 노출). 한 번 확인한 쪽지는 새로고침/재접속해도
 *   다시 자동 노출되지 않는다(백엔드 SSOT — 프론트는 안전망으로 한 번 더 필터).
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { useInboxPreview } from "../hooks/useInboxPreview";
import type { InboxMessageType } from "../types";
import styles from "./InboxPreviewDropdown.module.css";

const SESSION_KEY = "inbox_preview_dismissed";

const TYPE_LABEL: Record<InboxMessageType, string> = {
  notice: "공지",
  system: "시스템",
  billing: "결제",
};

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const min = Math.floor(diffMs / 60_000);
  if (min < 1) return "방금 전";
  if (min < 60) return `${min}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}일 전`;
  return new Date(iso).toLocaleDateString("ko-KR");
}

export function InboxPreviewDropdown() {
  const [open, setOpen] = useState(false);
  const { data, isPending, isError } = useInboxPreview();

  const unreadItems = data?.items.filter((it) => !it.is_read) ?? [];

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (sessionStorage.getItem(SESSION_KEY) === "1") return;
    if (unreadItems.length === 0) return;
    setOpen(true);
  }, [unreadItems.length]);

  function handleClose() {
    setOpen(false);
    if (typeof window !== "undefined") {
      sessionStorage.setItem(SESSION_KEY, "1");
    }
  }

  if (isPending || isError) return null;
  if (unreadItems.length === 0) return null;
  if (!open) return null;

  return (
    <div
      className={styles.dropdown}
      role="dialog"
      aria-label="쪽지함 미리보기"
    >
      <header className={styles.header}>
        <span className={styles.title}>쪽지함</span>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={handleClose}
          aria-label="미리보기 닫기"
        >
          ✕
        </button>
      </header>
      <ul className={styles.list}>
        {unreadItems.map((item) => (
          <li key={item.message_id}>
            <Link
              href={`/inbox?focus=${item.message_id}`}
              className={styles.item}
              onClick={handleClose}
            >
              <span className={styles.typeBadge} data-type={item.type}>
                {TYPE_LABEL[item.type]}
              </span>
              <span className={styles.itemBody}>
                <span className={styles.itemTitle}>{item.title}</span>
                <span className={styles.itemTime}>
                  {formatRelative(item.created_at)}
                </span>
              </span>
              {!item.is_read && (
                <span className={styles.unreadDot} aria-label="미읽음" />
              )}
            </Link>
          </li>
        ))}
      </ul>
      <footer className={styles.footer}>
        <Link
          href="/inbox"
          className={styles.viewAllLink}
          onClick={handleClose}
        >
          전체 쪽지함 보기 →
        </Link>
      </footer>
    </div>
  );
}

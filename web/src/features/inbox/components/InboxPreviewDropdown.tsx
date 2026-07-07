"use client";

/** 쪽지함 미리보기 드롭다운 — Story 7.1 → #118 재작업.
 *
 * 동작(#118):
 * - 안읽은 쪽지가 있는 계정이면 쪽지 아이콘 밑에 "최신 안읽은 쪽지 1건"을 자동 노출.
 * - 해당 쪽지를 읽기 전까지는 페이지를 이동해도 매 화면마다 계속 표시된다.
 *   (기존 sessionStorage 세션당 1회 정책 폐기 — 읽음 처리만이 영구 해제)
 * - X(닫기)는 현재 페이지에서만 접히고, 다른 페이지로 이동하면 다시 노출.
 * - 카드 클릭 → /inbox 로 이동(해당 메시지로 스크롤은 ?focus=<id>) → 읽음 처리되면
 *   preview 쿼리 invalidate 로 자동으로 사라진다.
 * - 미읽음 0건이면 렌더 안 함(아이콘만 노출). 백엔드가 미읽음만 응답하는 게 SSOT,
 *   프론트는 안전망으로 한 번 더 필터.
 */

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useInboxPreview } from "../hooks/useInboxPreview";
import type { InboxMessageType } from "../types";
import styles from "./InboxPreviewDropdown.module.css";

const TYPE_LABEL: Record<InboxMessageType, string> = {
  notice: "공지",
  system: "시스템",
  billing: "결제",
  admin_dm: "안내",
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
  const pathname = usePathname();
  // X로 닫으면 현재 페이지에서만 숨긴다 — 페이지 이동 시 다시 노출(#118).
  // (effect 대신 렌더 중 상태 보정 패턴 — pathname 이 바뀌면 dismissed 를 리셋)
  const [dismissed, setDismissed] = useState(false);
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setDismissed(false);
  }
  const { data, isPending, isError } = useInboxPreview();

  // 서버 응답은 미읽음 최신순 — 최신 1건만 미리보기로 노출한다(#118).
  const latestUnread = data?.items.find((it) => !it.is_read) ?? null;

  if (isPending || isError) return null;
  if (latestUnread === null) return null;
  if (dismissed) return null;

  return (
    <div
      className={styles.dropdown}
      role="dialog"
      aria-label="쪽지함 미리보기"
    >
      <header className={styles.header}>
        <span className={styles.title}>새 쪽지</span>
        <button
          type="button"
          className={styles.closeBtn}
          onClick={() => setDismissed(true)}
          aria-label="미리보기 닫기"
        >
          ✕
        </button>
      </header>
      <ul className={styles.list}>
        <li>
          <Link
            href={`/inbox?focus=${latestUnread.message_id}`}
            className={styles.item}
            onClick={() => setDismissed(true)}
          >
            <span className={styles.typeBadge} data-type={latestUnread.type}>
              {TYPE_LABEL[latestUnread.type]}
            </span>
            <span className={styles.itemBody}>
              <span className={styles.itemTitle}>{latestUnread.title}</span>
              <span className={styles.itemTime}>
                {formatRelative(latestUnread.created_at)}
              </span>
            </span>
            <span className={styles.unreadDot} aria-label="미읽음" />
          </Link>
        </li>
      </ul>
      <footer className={styles.footer}>
        <Link
          href="/inbox"
          className={styles.viewAllLink}
          onClick={() => setDismissed(true)}
        >
          전체 쪽지함 보기 →
        </Link>
      </footer>
    </div>
  );
}

"use client";

/** 받은 쪽지함 페이지 — Story 4.5 (F-503).
 *
 * 인증 가드: /my와 동일 — store만 보면 SessionBootstrap async 복원 전에 user=null
 * 짧은 구간이 생겨 유효 세션 사용자도 홈으로 튕긴다. ["session"] query를 직접 구독해
 * pending 동안에는 null 렌더링, isError 확정 시에만 팝업/리다이렉트.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { TopNav } from "@/components/layout/TopNav";
import { InboxList } from "@/features/inbox/components/InboxList";
import { useUnreadCount } from "@/features/inbox/hooks/useUnreadCount";
import type { InboxFilter } from "@/features/inbox/types";
import { fetchMe } from "@/features/auth/api";
import { useSessionStore } from "@/stores/session-store";

import styles from "./page.module.css";

export default function InboxPage() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);
  const [filter, setFilter] = useState<InboxFilter>("all");

  const { isLoading, data, isError } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const { data: unread } = useUnreadCount();

  useEffect(() => {
    if (!isLoading && isError && user == null) {
      openPopup("email");
      router.replace("/?login=required");
    }
  }, [isLoading, isError, user, openPopup, router]);

  if ((isLoading && user == null) || (data == null && user == null)) {
    return null;
  }

  const unreadCount = unread?.unread_count ?? 0;

  return (
    <>
      <TopNav />
      <main className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.heading}>받은 쪽지함</h1>
          <div
            role="tablist"
            aria-label="필터"
            className={styles.filterTabs}
          >
            <button
              type="button"
              role="tab"
              aria-selected={filter === "all"}
              onClick={() => setFilter("all")}
              className={`${styles.filterTab} ${filter === "all" ? styles.filterTabActive : ""}`}
            >
              전체
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={filter === "unread"}
              onClick={() => setFilter("unread")}
              className={`${styles.filterTab} ${filter === "unread" ? styles.filterTabActive : ""}`}
            >
              안 읽음 {unreadCount > 0 ? `${unreadCount}개` : ""}
            </button>
          </div>
        </header>
        <InboxList filter={filter} />
      </main>
    </>
  );
}

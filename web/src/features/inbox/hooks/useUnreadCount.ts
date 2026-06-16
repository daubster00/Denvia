"use client";

/** TopNav 미읽음 뱃지용 카운트 훅 — Story 4.5.
 *
 * #106(2026-06-16): 실시간 폴링/웹소켓 없이도, 사용자가 새로고침(F5) 하지 않고
 * 앱 내에서 페이지를 이동(=URL 변경)하면 그 시점에 미읽음 개수를 다시 조회한다.
 * 이상로그 탐지로 도착한 쪽지가 새로고침 전엔 안 보이던 문제 해결.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/stores/session-store";
import { fetchUnreadCount } from "../api";

export function useUnreadCount() {
  const user = useSessionStore((s) => s.user);
  const pathname = usePathname();
  const query = useQuery({
    queryKey: ["me", "inbox", "unread-count"],
    queryFn: fetchUnreadCount,
    enabled: user !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  // 라우트(URL)가 바뀔 때마다 미읽음 개수를 다시 조회한다. staleTime 과 무관하게
  // 강제 refetch — 페이지 전환만으로 새 쪽지 뱃지가 갱신되게 한다. 최초 마운트
  // (이전 pathname 없음)에는 useQuery 의 기본 조회로 충분하므로 건너뛴다.
  const prevPathname = useRef<string | null>(null);
  useEffect(() => {
    if (user === null) {
      prevPathname.current = pathname;
      return;
    }
    if (prevPathname.current !== null && prevPathname.current !== pathname) {
      void query.refetch();
    }
    prevPathname.current = pathname;
    // query 객체 전체를 deps 에 넣으면 매 렌더마다 effect 가 돌므로 refetch 만 의존.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, user]);

  return query;
}

"use client";

/** 쪽지함 미리보기 드롭다운용 데이터 훅 — Story 7.1.
 *
 * 서버가 동시 노출 최대 개수를 강제하므로 클라이언트는 limit를 보내지 않는다.
 * 로그인 상태에서만 활성화되며, 새 쪽지가 도착하면 inbox/unread-count invalidation에
 * 맞춰 자동으로 리프레시된다.
 *
 * #106(2026-06-16): 페이지 전환(URL 변경) 시점에도 다시 조회한다. 새로고침 없이
 * 앱 내 이동만으로 새로 도착한 쪽지(이상로그 탐지 등)가 드롭다운에 반영되게 한다.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/stores/session-store";
import { fetchInboxPreview } from "../api";

export function useInboxPreview() {
  const user = useSessionStore((s) => s.user);
  const pathname = usePathname();
  const query = useQuery({
    queryKey: ["me", "inbox", "preview"],
    queryFn: fetchInboxPreview,
    enabled: user !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, user]);

  return query;
}

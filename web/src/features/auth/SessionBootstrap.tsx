"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe } from "./api";
import { useSessionStore } from "@/stores/session-store";

/**
 * 앱 마운트 시 GET /api/v1/me로 세션 복원.
 * 401 → clearSession (비로그인 랜딩은 팝업 자동 오픈 안 함 — `?login=required` 쿼리로만 오픈).
 * subscription_status='blocked' → /blocked 리다이렉트 (FR45).
 *
 * 페이지 이동 감지:
 * - pathname 이 바뀌면 ["session"] 쿼리를 invalidate 하여 /api/v1/me 재호출.
 *   백엔드 SessionRefreshMiddleware 가 매 요청마다 쿠키 TTL 을 연장하므로
 *   페이지 이동만으로도 세션이 살아있게 된다. 만료된 경우엔 401 → 비로그인 상태 갱신.
 *
 * `?login=required` 진입 처리:
 * - api-client.ts 가 보호 페이지에서 401 감지 시 `/?login=required` 로 리다이렉트 후
 *   여기서 팝업을 자동 오픈한다.
 */
export function SessionBootstrap({ children }: { children: React.ReactNode }) {
  const setUser = useSessionStore((s) => s.setUser);
  const clearSession = useSessionStore((s) => s.clearSession);
  const openPopup = useSessionStore((s) => s.openPopup);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const popupHandledRef = useRef(false);

  const { data, isError } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (data) {
      setUser(data);
      if (data.subscription_status === "blocked") {
        router.push("/blocked");
      } else if (
        data.must_reset_password &&
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/reset-password")
      ) {
        router.push("/reset-password");
      }
    }
  }, [data, setUser, router]);

  useEffect(() => {
    if (isError) {
      clearSession();
    }
  }, [isError, clearSession]);

  // 페이지 이동마다 세션 재확인 — /admin/* 은 별도 admin layout 이 담당하므로 제외.
  useEffect(() => {
    if (!pathname || pathname.startsWith("/admin")) return;
    queryClient.invalidateQueries({ queryKey: ["session"] });
  }, [pathname, queryClient]);

  // /?login=required 진입 시 로그인 팝업 자동 오픈 + 쿼리스트링 정리.
  const loginRequired = searchParams.get("login");
  useEffect(() => {
    if (loginRequired !== "required") {
      popupHandledRef.current = false;
      return;
    }
    if (popupHandledRef.current) return;
    popupHandledRef.current = true;
    openPopup("email");
    const remaining = new URLSearchParams(searchParams.toString());
    remaining.delete("login");
    const nextQuery = remaining.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname || "/");
  }, [loginRequired, openPopup, pathname, router, searchParams]);

  return <>{children}</>;
}

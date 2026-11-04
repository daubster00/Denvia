"use client";

import { Suspense, useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe } from "./api";
import { useAlertStore } from "@/stores/alert-store";
import { useSessionStore } from "@/stores/session-store";
import { useQAStore } from "@/stores/qa-store";
import {
  isAuthFailure,
  resetClientSession,
} from "@/features/auth/lib/session-reset";

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
 * - useSearchParams 사용 컴포넌트는 prerender 시 Suspense 경계가 필요 (Next.js 16).
 */
export function SessionBootstrap({ children }: { children: React.ReactNode }) {
  const setUser = useSessionStore((s) => s.setUser);
  // 3차 검수 P1-1 — 일시 장애(5xx·네트워크)에서는 로그인 상태만 비우고 대화는 남긴다.
  const clearSession = useSessionStore((s) => s.clearSession);
  // 검수 P0-4 — QA 대화는 sessionStorage 에 남는다. 세션의 주인이 바뀌거나 세션이
  // 끝나면 이전 사용자의 대화가 다음 사용자의 질문 맥락으로 넘어가지 않게 비운다.
  // 같은 사용자의 새로고침·페이지 이동에서는 그대로 유지한다(setOwner 가 판정).
  const setQaOwner = useQAStore((s) => s.setOwner);
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();

  // /admin/* 페이지에서는 user me 호출 자체를 막는다.
  // 같은 브라우저에 남아 있던 일반 사이트 쿠키가 다른 디바이스 로그인으로 SUPERSEDED 401 을 받으면
  // api-client 가 /?login=superseded 로 강제 리다이렉트하면서 관리자 작업 화면이 튕기고,
  // 죽은 쿠키가 그대로 다시 전송되어 무한 루프가 된다. admin 페이지는 별도 admin layout 이
  // ["admin-session"] 쿼리로 자기 인증을 관리하므로 여기서는 user me 가 불필요.
  const isAdminRoute = pathname?.startsWith("/admin") ?? false;

  const { data, isError, error } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: !isAdminRoute,
  });

  useEffect(() => {
    if (data) {
      setUser(data);
      // 같은 사용자면 아무것도 지우지 않는다(새로고침·페이지 이동에서 대화 유지).
      // 다른 user_id 가 들어오면 이전 대화를 즉시 비운다.
      setQaOwner(data.user_id);
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
  }, [data, setUser, router, setQaOwner]);

  useEffect(() => {
    if (!isError) return;
    // 재수정 P0-2 — 로그인 세션과 QA 대화를 같은 함수로 함께 비운다.
    //
    // 3차 검수 P1-1 — 단, **인증 실패일 때만** 대화를 비운다. `isError` 는
    // 500·502·네트워크 단절에서도 참이 되는데, 그 전부를 세션 종료로 취급하면
    // 배포 중 20초간의 502 만으로 진행 중인 대화가 통째로 사라졌다(sessionStorage
    // 를 지우므로 서버가 복구돼도 돌아오지 않는다). 일시 장애에서는 로그인 상태만
    // 비우고 대화는 보존해, 다음 `/me` 성공에서 그대로 이어가게 한다.
    if (isAuthFailure(error)) {
      resetClientSession("bootstrap_failed");
    } else {
      clearSession();
    }
  }, [isError, error, clearSession]);

  // 페이지 이동마다 세션 재확인 — /admin/* 은 별도 admin layout 이 담당하므로 제외.
  useEffect(() => {
    if (!pathname || pathname.startsWith("/admin")) return;
    queryClient.invalidateQueries({ queryKey: ["session"] });
  }, [pathname, queryClient]);

  return (
    <>
      <Suspense fallback={null}>
        <LoginRequiredHandler />
      </Suspense>
      {children}
    </>
  );
}

function LoginRequiredHandler() {
  const openPopup = useSessionStore((s) => s.openPopup);
  const showAlert = useAlertStore((s) => s.show);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const popupHandledRef = useRef(false);

  const loginRequired = searchParams.get("login");
  useEffect(() => {
    if (loginRequired !== "required" && loginRequired !== "superseded") {
      popupHandledRef.current = false;
      return;
    }
    if (popupHandledRef.current) return;
    popupHandledRef.current = true;

    if (loginRequired === "superseded") {
      // 다른 장소에서 같은 계정으로 로그인되어 이 세션이 무효화된 경우.
      // 재수정 P0-2 — 이 경로도 세션 종료다. QA 대화까지 함께 비운다.
      // (api-client 리다이렉트를 거치지 않고 `?login=superseded` 로 직접 들어오는
      //  경우가 있어, 여기서도 같은 공통 함수를 호출해야 한 길도 빠지지 않는다)
      resetClientSession("superseded");
      showAlert({
        level: "warning",
        title: "다른 장소에서 로그인되어 로그아웃되었습니다.",
        dedupeKey: "session-superseded",
        actions: [
          {
            label: "확인",
            onClick: () => openPopup("email"),
          },
        ],
      });
    } else {
      openPopup("email");
    }

    const remaining = new URLSearchParams(searchParams.toString());
    remaining.delete("login");
    const nextQuery = remaining.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname || "/");
  }, [loginRequired, openPopup, showAlert, pathname, router, searchParams]);

  return null;
}

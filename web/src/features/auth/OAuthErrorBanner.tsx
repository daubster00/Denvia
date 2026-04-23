"use client";

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { getErrorMessage } from "@/lib/error-copy";
import { useAlertStore } from "@/stores/alert-store";

/**
 * URL `?oauth_error=...` 감지 → 글로벌 AppAlert로 디스패치 + 쿼리 제거.
 *
 * UI를 직접 그리지 않고 store에 푸시만 한다. 같은 코드가 router.replace로
 * 쿼리 제거 시 useEffect가 재실행돼도 dedupeKey로 중복 방지.
 */
export function OAuthErrorBanner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const show = useAlertStore((s) => s.show);
  const lastHandledRef = useRef<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("oauth_error");
    if (!code) return;
    if (lastHandledRef.current === code) return;

    lastHandledRef.current = code;
    show({
      level: "error",
      title: "로그인 안내",
      description: getErrorMessage(code),
      dedupeKey: `oauth_error:${code}`,
    });

    // URL에서 oauth_error 쿼리만 제거하여 새로고침 시 중복 표시 방지
    const remaining = new URLSearchParams(searchParams.toString());
    remaining.delete("oauth_error");
    const nextQuery = remaining.toString();
    const pathname =
      typeof window !== "undefined" ? window.location.pathname : "/";
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  }, [searchParams, router, show]);

  // 다음 에러가 같은 코드여도 다시 표시되도록, 페이지 이탈 시 ref 리셋
  useEffect(() => {
    return () => {
      lastHandledRef.current = null;
    };
  }, []);

  return null;
}

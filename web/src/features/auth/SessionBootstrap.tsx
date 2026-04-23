"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "./api";
import { useSessionStore } from "@/stores/session-store";

/**
 * 앱 마운트 시 GET /api/v1/me로 세션 복원.
 * 401 → clearSession (팝업 자동 오픈 금지 — 비로그인 랜딩은 정상 경로).
 * subscription_status='blocked' → /blocked 리다이렉트 (FR45).
 */
export function SessionBootstrap({ children }: { children: React.ReactNode }) {
  const setUser = useSessionStore((s) => s.setUser);
  const clearSession = useSessionStore((s) => s.clearSession);
  const router = useRouter();

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
      // 401 시 팝업 자동 오픈 금지 (비로그인 랜딩 정상 경로 — architecture.md §855)
    }
  }, [isError, clearSession]);

  return <>{children}</>;
}

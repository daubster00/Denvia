"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSessionStore } from "@/stores/session-store";
import { fetchMe } from "@/features/auth/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const openPopup = useSessionStore((s) => s.openPopup);

  // 인증 판단은 useQuery 결과를 직접 사용 — store의 user는 SessionBootstrap useEffect 다음 tick에서야 채워지므로
  // 캐시 hit 시 store sync race로 잠깐 user=null이 되어 팝업이 깜빡이는 문제 회피.
  const { isLoading, data, isError } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!isLoading && isError) {
      openPopup("email");
    }
  }, [isLoading, isError, openPopup]);

  if (isLoading || !data) {
    return null;
  }

  return <>{children}</>;
}

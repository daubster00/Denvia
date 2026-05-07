"use client";

/** 메인 진입 시 노출 후보 팝업 배열 — Story 7.2 v2. */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/stores/session-store";
import { fetchActivePopups } from "../api";
import { detectDevice } from "../lib/popup-dismissal";

export function useActivePopups() {
  const user = useSessionStore((s) => s.user);
  // 마운트 후에만 정확한 디바이스 결정 — SSR 시점에 잘못 잡히지 않도록.
  const [device, setDevice] = useState<"pc" | "mobile" | null>(null);

  useEffect(() => {
    setDevice(detectDevice());
  }, []);

  return useQuery({
    queryKey: ["me", "popups", "active", device],
    queryFn: () => fetchActivePopups(device ?? "pc"),
    enabled: user !== null && device !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 0,
  });
}

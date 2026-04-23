"use client";

import { useSessionStore } from "@/stores/session-store";
import { LoginPopup } from "./LoginPopup";

/** 전역 단일 인스턴스 — isPopupOpen을 구독하여 LoginPopup을 조건부 렌더 */
export function LoginPopupMount() {
  const isOpen = useSessionStore((s) => s.isPopupOpen);
  if (!isOpen) return null;
  return <LoginPopup />;
}

"use client";

import { useSessionStore } from "@/stores/session-store";
import { LoginPopup } from "./LoginPopup";

/**
 * 전역 단일 인스턴스 — isPopupOpen을 구독하여 LoginPopup을 조건부 렌더.
 *
 * body scroll lock은 의도적으로 사용하지 않는다 — 외부 이동(window.location.href)
 * 후 복귀 시 lock이 잔류하여 UI 먹통이 되는 이슈 회피. 백드롭(z-index 999)이
 * 전체 뷰포트를 덮어 뒤 배경 인터랙션을 물리적으로 차단하므로 UX상 손실 없음.
 */
export function LoginPopupMount() {
  const isOpen = useSessionStore((s) => s.isPopupOpen);
  if (!isOpen) return null;
  return <LoginPopup />;
}

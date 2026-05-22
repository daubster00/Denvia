"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SessionUser } from "@/types/api";

interface SessionState {
  user: SessionUser | null;
  preferPersist: boolean;
  isPopupOpen: boolean;
  popupInitialTab: "email" | "social";
  /**
   * 비밀번호 오류 반복으로 hard_lock(AUTH_MUST_RESET_PASSWORD) 응답을 받은 후
   * 사용자가 안내를 확인한 상태. true 이면 LoginPopup 이 자동으로
   * 비밀번호 찾기 뷰로 시작한다. 비밀번호 찾기 폼이 제출 완료되면 자동 해제.
   */
  forcePasswordReset: boolean;
  setUser: (u: SessionUser | null) => void;
  clearSession: () => void;
  setPreferPersist: (v: boolean) => void;
  openPopup: (tab?: "email" | "social") => void;
  closePopup: () => void;
  setForcePasswordReset: (v: boolean) => void;
}

/**
 * 전역 세션 상태 — 유저 정보 · 팝업 open 상태 · "로그인 상태 유지" 선호.
 * preferPersist / forcePasswordReset 은 sessionStorage 에 persist (탭 생명주기 내 유지).
 */
export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      user: null,
      preferPersist: false,
      isPopupOpen: false,
      popupInitialTab: "email",
      forcePasswordReset: false,
      setUser: (u) => set({ user: u }),
      clearSession: () => set({ user: null }),
      setPreferPersist: (v) => set({ preferPersist: v }),
      // 팝업이 열릴 때마다 비번찾기 강제 모드를 해제한다. 2차 락 직후엔 EmailLoginTab 이
      // 다시 setForcePasswordReset(true) 로 활성화하므로, 관리자 잠금 해제 후 사용자가
      // 다시 로그인 시도할 때만 정상 폼이 노출된다. 영구 강제 모드가 sessionStorage 에
      // 남아 비번찾기 화면에서만 갇히는 버그를 막는다.
      openPopup: (tab = "email") =>
        set({ isPopupOpen: true, popupInitialTab: tab, forcePasswordReset: false }),
      closePopup: () => set({ isPopupOpen: false }),
      setForcePasswordReset: (v) => set({ forcePasswordReset: v }),
    }),
    {
      name: "denvia-session-store",
      storage: createJSONStorage(() => sessionStorage),
      // sessionStorage 에만 저장 — localStorage 금지 (NFR-S4).
      partialize: (s) => ({
        preferPersist: s.preferPersist,
        forcePasswordReset: s.forcePasswordReset,
      }),
    }
  )
);

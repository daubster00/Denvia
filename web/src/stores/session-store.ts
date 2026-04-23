"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SessionUser } from "@/types/api";

interface SessionState {
  user: SessionUser | null;
  preferPersist: boolean;
  isPopupOpen: boolean;
  popupInitialTab: "email" | "social";
  setUser: (u: SessionUser | null) => void;
  clearSession: () => void;
  setPreferPersist: (v: boolean) => void;
  openPopup: (tab?: "email" | "social") => void;
  closePopup: () => void;
}

/**
 * 전역 세션 상태 — 유저 정보 · 팝업 open 상태 · "로그인 상태 유지" 선호.
 * preferPersist만 sessionStorage에 persist (탭 생명주기 내 유지).
 */
export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      user: null,
      preferPersist: false,
      isPopupOpen: false,
      popupInitialTab: "email",
      setUser: (u) => set({ user: u }),
      clearSession: () => set({ user: null }),
      setPreferPersist: (v) => set({ preferPersist: v }),
      openPopup: (tab = "email") => set({ isPopupOpen: true, popupInitialTab: tab }),
      closePopup: () => set({ isPopupOpen: false }),
    }),
    {
      name: "denvia-session-store",
      storage: createJSONStorage(() => sessionStorage),
      // preferPersist만 세션스토리지에 저장 — localStorage 금지 (NFR-S4)
      partialize: (s) => ({ preferPersist: s.preferPersist }),
    }
  )
);
